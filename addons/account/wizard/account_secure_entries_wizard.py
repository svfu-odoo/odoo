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
        related="company_id.account_fiscal_country_id.code",
    )
    hash_date = fields.Date(
        string='Hash All Entries',
        required=True,
        help="The selected Date",
    )
    chains_to_hash_with_gaps= fields.Json(
        compute='_compute_data',
    )
    max_hash_date = fields.Date(
        string='Max Hash Date',
        compute='_compute_max_hash_date',
        help="Highest Date such that all posted journal entries prior to (including) the date are secured. Only journal entries after the hard lock date are considered.",
    )
    unreconciled_bank_statement_line_ids = fields.Many2many(
        compute='_compute_data',
        comodel_name='account.bank.statement.line',
        help="All unreconciled bank statement lines before the selected date.",
    )
    not_hashable_unlocked_move_ids = fields.Many2many(
        compute='_compute_data',
        comodel_name='account.move',
        help="All unhashable moves before the selected date that are not protected by the Hard Lock Date",
    )
    move_to_hash_ids = fields.Many2many(
        compute='_compute_data',
        comodel_name='account.move',
        help="All moves that will be hashed",
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
            chains_to_hash = wizard._get_chains_to_hash(wizard.company_id, today)
            moves = self.env['account.move'].concat(
                *[chain['moves'] for chain in chains_to_hash],
                *[chain['not_hashable_unlocked_moves'] for chain in chains_to_hash],
            )
            if moves:
                wizard.max_hash_date = min(move.date for move in moves) - timedelta(days=1)
            else:
                wizard.max_hash_date = False

    @api.model
    def _jsonify_chains_to_hash(self, chains_to_hash):
        self.ensure_one()
        return [{key}]

    @api.model
    def _get_chains_to_hash(self, company_id, hash_date, extra_domain=None):
        self.ensure_one()
        res = []
        extra_domain = expression.AND([extra_domain or [], [('state', '=', 'posted')]])
        moves = self.env['account.move'].sudo().search(
            self._get_unhashed_moves_in_hashed_period_domain(company_id, hash_date, extra_domain)
        )
        for journal, journal_moves in moves.grouped('journal_id').items():
            for chain_moves in journal_moves.grouped('sequence_prefix').values():
                chain_info = chain_moves._get_chain_info(force_hash=True)
                if chain_info is False:
                    continue
                last_move_hashed = chain_info['last_move_hashed']
                # It is possible that some moves cannot be hashed (i.e. after upgrade).
                # We show a warning ('account_not_hashable_unlocked_moves') if that is the case.
                # These moves are ignored for the warning and max_hash_date in case they are protected by the Hard Lock Date
                if last_move_hashed:
                    # remaining_moves either have a hash already or have a higher sequence_number than the last_move_hashed
                    not_hashable_unlocked_moves = chain_info['remaining_moves'].filtered(
                        lambda move: (not move.inalterable_hash
                                      and move.sequence_number < last_move_hashed.sequence_number
                                      and move.date > self.company_id.user_hard_lock_date)
                    )
                else:
                    not_hashable_unlocked_moves = self.env['account.move']
                chain_info['not_hashable_unlocked_moves'] = not_hashable_unlocked_moves
                res.append(chain_info)
                # res[(journal, chain_moves[0].sequence_prefix)] = chain_info
        return res

    @api.depends('company_id', 'company_id.user_hard_lock_date', 'hash_date')
    def _compute_data(self):
        for wizard in self:
            unreconciled_bank_statement_line_ids = []
            chains_to_hash = []
            if wizard.hash_date:
                unreconciled_bank_statement_lines = self.env['account.bank.statement.line'].search(
                    wizard.company_id._get_unreconciled_statement_lines_domain(wizard.hash_date)
                )
                unreconciled_bank_statement_line_ids = unreconciled_bank_statement_lines.ids
                extra_domain = [('sequence_prefix', 'not in', unreconciled_bank_statement_lines.move_id.mapped('sequence_prefix'))]
                chains_to_hash = wizard._get_chains_to_hash(wizard.company_id, wizard.hash_date, extra_domain=extra_domain)
            wizard.unreconciled_bank_statement_line_ids = [Command.set(unreconciled_bank_statement_line_ids)]
            wizard.chains_to_hash_with_gaps = [
                {
                    'first_move_id': chain['moves'][0].id,
                    'last_move_id': chain['moves'][-1].id,
                } for chain in chains_to_hash if 'gap' in chain['warnings']
            ]

            not_hashable_unlocked_moves = []
            move_to_hash_ids = []
            for chain in chains_to_hash:
                not_hashable_unlocked_moves.extend(chain['not_hashable_unlocked_moves'].ids)
                move_to_hash_ids.extend(chain['moves'].ids)
            wizard.not_hashable_unlocked_move_ids = [Command.set(not_hashable_unlocked_moves)]
            wizard.move_to_hash_ids = [Command.set(move_to_hash_ids)]

    @api.depends('company_id', 'chains_to_hash_with_gaps', 'hash_date', 'not_hashable_unlocked_move_ids', 'max_hash_date', 'unreconciled_bank_statement_line_ids')
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

            not_hashable_unlocked_moves = wizard.not_hashable_unlocked_move_ids
            if not_hashable_unlocked_moves:
                warnings['account_not_hashable_unlocked_moves'] = {
                    'message': _("There are entries that cannot be hashed. They can be protected by the Hard Lock Date."),
                    'action_text': _("Review"),
                    'action': wizard.action_show_moves(not_hashable_unlocked_moves),
                }

            # chains_to_hash = wizard.chains_to_hash or []
            # chains_with_gaps = [chain for chain in chains_to_hash if 'gap' in chain['warnings']]
            if wizard.chains_to_hash_with_gaps:
                OR_domains = []
                for chain in wizard.chains_to_hash_with_gaps:
                    first_move = self.env['account.move'].browse(chain['first_move_id'])
                    last_move = self.env['account.move'].browse(chain['last_move_id'])
                    OR_domains.append([
                        *self.env['account.move']._check_company_domain(wizard.company_id),
                        ('journal_id', '=', last_move.journal_id.id),
                        ('sequence_prefix', '=', last_move.sequence_prefix),
                        ('sequence_number', '<=', last_move.sequence_number),
                        ('sequence_number', '>=', first_move.sequence_number),
                    ])
                domain = expression.OR(OR_domains)
                warnings['account_sequence_gap'] = {
                    'message': _("Securing these entries will create at least one gap in the sequence."),
                    'action_text': _("Review"),
                    'action': {
                        **self.env['account.journal']._show_sequence_holes(domain),
                        'views': [[self.env.ref('account.view_move_tree_multi_edit').id, 'list'], [self.env.ref('account.view_move_form').id, 'form']],
                    }
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

        self.env['res.groups']._activate_group_account_secured()

        if not self.move_to_hash_ids:
            return

        self.move_to_hash_ids._hash_moves(force_hash=True, raise_if_gap=False)
