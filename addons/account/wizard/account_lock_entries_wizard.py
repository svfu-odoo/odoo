from odoo import api, fields, models, _

from odoo.exceptions import RedirectWarning


class AccountLockEntries(models.TransientModel):
    """
    This wizard is used to lock journal entries (with a hash)
    """
    _name = 'account.lock.entries.wizard'
    _description = 'Lock Journal Entries (with a Hash)'

    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        readonly=True,
        default=lambda self: self.env.company,
    )

    hash_date = fields.Date(
        string='Hash All Entries',
    )

    show_draft_entries_warning = fields.Text(
        string="Show Draft Entries Warning",
        compute='_compute_show_draft_entries_warning',
    )

    def _get_moves_in_hashed_period_domain(self, state='posted'):
        """
        Return the domain to find all moves before `self.hash_date` that have not been hashed yet.
        We ignore whether hashing is activated for the journal or not.
        :param state: The state of the moves that we consider.
            Can i.e. be used to check whether there are still moves in draft.
        :return a search domain
        """
        self.ensure_one()
        if not self.hash_date:
            return [(0, '=', 1)]
        return [
            ('date', '<=', self.hash_date),
            ('company_id', 'child_of', self.company.id),
            ('inalterable_hash', '=', False),
            ('state', '=', state),
        ]

    def _get_draft_moves_in_hashed_period_domain(self):
        self.ensure_one()
        return self._get_moves_in_hashed_period_domain(state='draft')

    @api.depends('hash_date')
    def _compute_show_draft_entries_warning(self):
        for wizard in self:
            draft_entries = self.env['account.move'].search(self._get_draft_moves_in_hashed_period_domain(), limit=1)
            wizard.show_draft_entries_warning = bool(draft_entries)

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

    def validate_hash_date(self):
        self.ensure_one()
        unreconciled_statement_lines = self.env['account.bank.statement.line'].search(
            self.company_id._get_unreconciled_statement_lines_domain(self.hash_date)
        )
        if unreconciled_statement_lines:
            error_msg = _("There are still unreconciled bank statement lines in the period you want to lock."
                          "You should either reconcile or delete them.")
            action_error = self._get_unreconciled_statement_lines_redirect_action(unreconciled_statement_lines)
            raise RedirectWarning(error_msg, action_error, _('Show Unreconciled Bank Statement Line'))

    def action_lock_entries(self):
        self.ensure_one()

        self.validate_hash_date()

        moves = self.env['account.move'].search(self._get_moves_in_hashed_period_domain(state='posted'))

        moves.button_hash()
