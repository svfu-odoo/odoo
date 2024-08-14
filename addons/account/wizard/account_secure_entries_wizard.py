from datetime import timedelta

from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError
from odoo.osv import expression
from odoo.tools import format_list
from odoo.tools.misc import format_date


class AccountSecureEntries(models.TransientModel):
    """
    This wizard is used to secure journal entries (with a hash)
    """
    _name = 'account.secure.entries.wizard'
    _description = 'Secure Journal Entries'

    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        readonly=True,
        default=lambda self: self.env.company,
    )
    country_code = fields.Char(
        related="company_id.account_fiscal_country_id.code"
    )
    hash_date = fields.Date(
        string='Hash All Entries',
        required=True,
    )
    max_hash_date = fields.Date(
        string='Max Hash Date',
        compute='_compute_max_hash_date',
        help="Highest Date such that all posted journal entries prior to (including) the date are secured. Only journal entries after the hard lock date are considered."
    )
    unreconciled_bank_statement_line_ids = fields.Many2many(
        compute='_compute_data',
        comodel_name='account.bank.statement.line'
    )
    move_ids = fields.Many2many(
        compute='_compute_data',
        comodel_name='account.move'
    )
    not_hashable_move_ids = fields.Many2many(
        compute='_compute_data',
        comodel_name='account.move'
    )
    move_to_hash_ids = fields.Many2many(
        compute='_compute_data',
        comodel_name='account.move'
    )
    warnings = fields.Json(
        compute='_compute_warnings',
    )

    def new(self, *args, **kwargs):
        res = super().new(*args, **kwargs)
        for wizard in res:
            if not wizard.company_id:
                wizard.company_id = self.env.company
            if not wizard.hash_date:
                wizard.hash_date = wizard.max_hash_date or fields.Date.context_today(self)
        return res

    @api.depends('company_id', 'company_id.user_hard_lock_date')
    def _compute_max_hash_date(self):
        today = fields.Date.context_today(self)
        for wizard in self:
            move_ids, _not_hashable_move_ids = wizard._get_move_ids(wizard.company_id, today)
            moves = self.env['account.move'].browse(move_ids)
            if moves:
                wizard.max_hash_date = min(move.date for move in moves) - timedelta(days=1)
            else:
                wizard.max_hash_date = False

    @api.model
    def _get_move_ids(self, company_id, hash_date, extra_domain=None):
        self.ensure_one()
        extra_domain = expression.AND([extra_domain or [], [('state', '=', 'posted')]])
        moves = self.env['account.move'].sudo().search(
            self._get_unhashed_moves_in_hashed_period_domain(company_id, hash_date, extra_domain)
        )
        move_ids = []
        not_hashable_move_ids = []
        for journal, journal_moves in moves.grouped('journal_id').items():
            for chain_moves in journal_moves.grouped('sequence_prefix').values():
                last_move_in_chain = chain_moves.sorted('sequence_number')[-1]
                if not self.env['account.move']._is_move_restricted(last_move_in_chain, force_hash=True):
                    continue
                last_move_hashed = self.env['account.move'].sudo().search([
                    ('journal_id', '=', journal.id),
                    ('sequence_prefix', '=', last_move_in_chain.sequence_prefix),
                    ('inalterable_hash', '!=', False),
                ], order='sequence_number desc', limit=1)
                # We ignore unhashed moves inside the sequence if they are protected by the hard lock date
                # TODO: what happens if no last_move_hashed found?
                if last_move_hashed:
                    chain_moves_to_hash = chain_moves.filtered_domain([
                        '|',
                            ('sequence_number', '>=', last_move_hashed.sequence_number),
                            ('date', '>', self.company_id.user_hard_lock_date),
                       ])
                else:
                    chain_moves_to_hash = chain_moves
                # TODO: ?: add the last move hashed for the gap test
                move_ids.extend(chain_moves_to_hash.ids)
                not_hashable_moves = chain_moves_to_hash.filtered_domain([
                    ('sequence_number', '<', last_move_hashed.sequence_number),
                ])
                not_hashable_move_ids.extend(not_hashable_moves.ids)
        return move_ids, not_hashable_move_ids

    @api.depends('company_id', 'company_id.user_hard_lock_date', 'hash_date')
    def _compute_data(self):
        for wizard in self:
            move_ids = []
            not_hashable_move_ids = []
            unreconciled_bank_statement_line_ids = []
            if wizard.hash_date:
                unreconciled_bank_statement_lines = self.env['account.bank.statement.line'].search(
                    wizard.company_id._get_unreconciled_statement_lines_domain(wizard.hash_date)
                )
                unreconciled_bank_statement_line_ids = unreconciled_bank_statement_lines.ids
                extra_domain = [('sequence_prefix', 'not in', unreconciled_bank_statement_lines.move_id.mapped('sequence_prefix'))]
                move_ids, not_hashable_move_ids = wizard._get_move_ids(wizard.company_id, wizard.hash_date, extra_domain=extra_domain)
            wizard.move_ids = [Command.set(move_ids)]
            wizard.unreconciled_bank_statement_line_ids = [Command.set(unreconciled_bank_statement_line_ids)]
            wizard.not_hashable_move_ids = [Command.set(not_hashable_move_ids)]
            wizard.move_to_hash_ids = wizard.move_ids - wizard.not_hashable_move_ids

    @api.depends('company_id', 'hash_date', 'not_hashable_move_ids', 'max_hash_date')
    def _compute_warnings(self):
        for wizard in self:
            warnings = {}

            if wizard.max_hash_date:
                max_hash_date_string = format_date(self.env, wizard.max_hash_date)
            else:
                max_hash_date_string = _("today")
            warnings['account_max_hash_date'] = {
                'message': _("Posted entries are currently secured up to %s, inclusive.", max_hash_date_string),
            }

            if not wizard.hash_date:
                wizard.warnings = warnings
                continue

            if wizard.unreconciled_bank_statement_line_ids:
                ignored_sequence_prefixes = list(set(wizard.unreconciled_bank_statement_line_ids.move_id.mapped('sequence_prefix')))
                warnings['account_unreconciled_bank_statement_line_ids'] = {
                    'message': _("There are still unreconciled bank statement lines before the selected date. "
                                 "The entries from journal prefixes containing them will not be secured: %(prefix_info)s",
                                 prefix_info=format_list(self.env, ignored_sequence_prefixes)),
                    'level': 'danger',
                    'action_text': _("Review"),
                    'action': wizard.company_id._get_unreconciled_statement_lines_redirect_action(wizard.unreconciled_bank_statement_line_ids),
                }

            if wizard.not_hashable_move_ids:
                warnings['account_not_hashable_move'] = {
                    'message': _("There are entries that cannot be hashed. They can be protected by via the Hard Lock Date."),
                    'action_text': _("Review"),
                    'action': wizard.action_show_moves(wizard.not_hashable_move_ids),
                }

            draft_entries = self.env['account.move'].search_count(
                wizard._get_draft_moves_in_hashed_period_domain(),
                limit=1
            )
            if draft_entries:
                warnings['account_unhashed_draft_entries'] = {
                    'message': _("There are still draft entries before the selected date."),
                    'action_text': _("Review"),
                    'action': wizard.action_show_draft_moves_in_hashed_period(),
                }

            gaps = wizard.move_to_hash_ids._get_gaps()
            if gaps:
                # TODO: remove:
                # Version where we only put the whole chain
                # gap_strings = []
                # for (seq_format, format_values), (first, last) in gaps.items():
                #     chain_first = seq_format.format(**{**format_values, 'seq': first})
                #     chain_last = seq_format.format(**{**format_values, 'seq': last})
                #     gap_strings.append(_("between %(chain_first)s and %(chain_last)s", chain_first=chain_first, chain_last=chain_last))
                # warnings['account_sequence_gap'] = {
                #     'message': _("Securing these entries will create at least one gap in the sequence: %(gap_info)s",
                #                  gap_info=format_list(self.env, gap_strings)),
                # }

                gap_strings = []
                for (seq_format, format_values), gap_list in gaps.items():
                    for predecessor_seq, seq in gap_list:
                        record = seq_format.format(**{**format_values, 'seq': seq})
                        predecessor_record = seq_format.format(**{**format_values, 'seq': predecessor_seq})
                        gap_strings.append(_("between %(predecessor_record)s and %(record)s",
                                             record=record, predecessor_record=predecessor_record))
                warnings['account_sequence_gap'] = {
                    'message': _("Securing these entries will create at least one gap in the sequence: %(gap_info)s",
                                 gap_info=format_list(self.env, gap_strings)),
                }

            wizard.warnings = warnings

    @api.model
    def _get_unhashed_moves_in_hashed_period_domain(self, company_id, hash_date, domain=False):
        """
        Return the domain to find all moves before `self.hash_date` that have not been hashed yet.
        We ignore whether hashing is activated for the journal or not.
        :return a search domain
        """
        if not (company_id and hash_date):
            return [(0, '=', 1)]
        return expression.AND([
            [
                ('date', '<=', fields.Date.to_string(hash_date)),
                ('company_id', 'child_of', company_id.id),
                ('inalterable_hash', '=', False),
            ],
            domain or [],
        ])

    def _get_draft_moves_in_hashed_period_domain(self):
        self.ensure_one()
        return self._get_unhashed_moves_in_hashed_period_domain(self.company_id, self.hash_date, [('state', '=', 'draft')])

    def action_show_moves(self, moves):
        self.ensure_one()
        return {
            'view_mode': 'tree',
            'name': _('Draft Entries'),
            'res_model': 'account.move',
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', moves.ids)],
            'search_view_id': [self.env.ref('account.view_account_move_filter').id, 'search'],
            'views': [[self.env.ref('account.view_move_tree_multi_edit').id, 'list'], [self.env.ref('account.view_move_form').id, 'form']],
        }

    def action_show_draft_moves_in_hashed_period(self):
        self.ensure_one()
        return {
            'view_mode': 'tree',
            'name': _('Draft Entries'),
            'res_model': 'account.move',
            'type': 'ir.actions.act_window',
            'domain': self._get_draft_moves_in_hashed_period_domain(),
            'search_view_id': [self.env.ref('account.view_account_move_filter').id, 'search'],
            'views': [[self.env.ref('account.view_move_tree_multi_edit').id, 'list'], [self.env.ref('account.view_move_form').id, 'form']],
        }

    def action_secure_entries(self):
        self.ensure_one()

        if not self.hash_date:
            raise UserError(_("Set a date. The moves will be secured up to including this date."))

        if not self.move_to_hash_ids:
            return

        self.move_to_hash_ids._hash_moves(force_hash=True, raise_if_gap=False)
