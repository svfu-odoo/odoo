from odoo import models, api, fields, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_de_state = fields.Selection(
        selection='_get_l10n_de_state_selection_values',
        string="State ",  # extra space to avoid name clash
        compute='_compute_l10n_de_state',
        search='_search_l10n_de_state',
    )

    @api.model
    def _get_l10n_de_state_selection_values(self):
        # Add the new state before the 'posted' state in the original 'state' values (for order in statusbar)
        original_values = self._fields['state']._description_selection(self.env)
        posted_index = next((i for i, value in enumerate(original_values) if value[0] == 'posted'), 1)
        return original_values[:posted_index] + [('validated', 'Validated')] + original_values[posted_index:]

    @api.depends('state', 'inalterable_hash')
    def _compute_l10n_de_state(self):
        for move in self:
            if move.state == 'posted':
                move.l10n_de_state = 'posted' if move.inalterable_hash else 'validated'
            else:
                move.l10n_de_state = move.state

    def _search_l10n_de_state(self, operator, value):
        if value not in [value for value, label in self._get_l10n_de_state_selection_values()]:
            raise UserError(_('Operation not supported'))
        if value not in ['validated', 'posted']:
            return [('state', operator, value)]
        if operator not in ['=', '!=']:
            raise UserError(_('Operation not supported'))

        # TODO: check move fiscal country?
        normal_domain_for_equals = []
        if value == 'validated':
            normal_domain_for_equals = [
                '&',
                    ('state', '=', 'posted'),
                    '&',
                        ('inalterable_hash', '=', False),
                        ('country_code', '=', 'DE'),
            ]
        elif value == 'posted':
            normal_domain_for_equals = [
                '&',
                    ('state', '=', 'posted'),
                    '|',
                        ('inalterable_hash', '!=', False),
                        ('country_code', '!=', 'DE'),
            ]
        if operator == '=':
            return normal_domain_for_equals
        else:
            return ['!'] + normal_domain_for_equals

    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if self.env.company.account_fiscal_country_id.code == 'DE':
            # TODO:?: replace state with l10n_de_state
            # TODO: adapt search and filter
            pass
        return arch, view
