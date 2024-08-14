from odoo import api, fields, models, _


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

    def _get_moves_to_hash_domain(self):
        self.ensure_one()
        if not self.hash_date:
            return [(0, '=', 1)]
        # TODO: like _get_move_hash_domain but without posted requirement
        return [
            ('date', '<=', self.hash_date),
            ('company_id', 'child_of', self.env.company.id),
            ('inalterable_hash', '=', False),
            ('restrict_mode_hash_table', '=', True),
        ]

    def _get_draft_moves_to_hash_domain(self):
        self.ensure_one()
        return self._get_moves_to_hash_domain() + [('state', '=', 'draft')]

    @api.depends('hash_date')
    def _compute_show_draft_entries_warning(self):
        for wizard in self:
            draft_entries = self.env['account.move'].search(self._get_draft_moves_to_hash_domain(), limit=1)
            wizard.show_draft_entries_warning = bool(draft_entries)

    def action_show_draft_moves_in_hashed_period(self):
        self.ensure_one()
        return {
            'view_mode': 'tree',
            'name': _('Draft Entries'),
            'res_model': 'account.move',
            'type': 'ir.actions.act_window',
            'domain': self._get_draft_moves_to_hash_domain(),
            'search_view_id': [self.env.ref('account.view_account_move_filter').id, 'search'],
            'views': [[self.env.ref('account.view_move_tree_multi_edit').id, 'list'], [self.env.ref('account.view_move_form').id, 'form']],
        }

    def action_lock_entries(self):
        self.ensure_one()
        moves = self.env['account.move'].search(self._get_moves_to_hash_domain())
        moves.button_hash()
