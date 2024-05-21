from odoo import api, models, _
from odoo.exceptions import UserError


class AccountTax(models.Model):
    _inherit = 'account.tax'

    @api.ondelete(at_uninstall=False)
    def _never_unlink_declaration_of_intent_tax(self):
        for company_id, taxes in self.grouped('company_id').items():
            declaration_tax = company_id.l10n_it_edi_doi_declaration_of_intent_tax
            if declaration_tax in taxes:
                raise UserError(_('You cannot delete the special tax for Declarations of Intent.'))
