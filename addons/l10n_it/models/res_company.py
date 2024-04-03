# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class ResCompany(models.Model):
    _name = 'res.company'
    _inherit = 'res.company'

    def _l10n_it_get_declaration_of_intent_fiscal_position(self):
        """
        Return the fiscal position to be used for an Invoice or Sales Order using a Declaration of Intent.
        """
        self.ensure_one()
        fiscal_position = self.env['account.chart.template'].with_company(self)\
            .ref('declaration_of_intent_fiscal_position', raise_if_not_found=False)
        return fiscal_position or self.env['account.fiscal.position']

    def _l10n_it_get_declaration_of_intent_tax(self):
        """
        Return the tax to be used for an Invoice or Sales Order line using a Declaration of Intent.
        """
        self.ensure_one()
        tax = self.env['account.chart.template'].with_company(self)\
            .ref('00di', raise_if_not_found=False)
        return tax or self.env['account.tax']
