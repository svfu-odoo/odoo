# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class AccountMoveLine(models.Model):

    _inherit = 'account.move.line'

    l10n_it_edi_doi_declaration_of_intent_id = fields.Many2one(
        related='move_id.l10n_it_edi_doi_declaration_of_intent_id',
        store=True,
    )

    def _l10n_it_edi_doi_get_declaration_amount(self, declaration):
        """
        Consider all the lines in self that belong to declaration of intent `declaration`
        and have the special declaration of intent tax applied.
        This function returns the sum of the price_total of all those lines
        (the tax amount of the lines is always 0).
        """
        if not declaration:
            return 0

        tax = declaration.company_id._l10n_it_edi_doi_get_declaration_of_intent_tax()
        if not tax:
            return 0

        relevant_self = self.filtered(
            lambda line: (line.l10n_it_edi_doi_declaration_of_intent_id == declaration
                          # The declaration tax cannot be used with other taxes on a single line
                          # (checked in `_post` of model 'account.move')
                          and line.tax_ids.ids == tax.ids)
        )
        amount = 0
        for move_type, lines in relevant_self.grouped('move_type').items():
            sign = 1 if move_type in self.env['account.move'].get_inbound_types(include_receipts=True) else -1
            amount += sign * sum(lines.mapped('price_total'))
        return amount
