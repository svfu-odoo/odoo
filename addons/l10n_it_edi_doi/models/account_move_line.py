# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import api, fields, models


class AccountMoveLine(models.Model):

    _inherit = 'account.move.line'

    l10n_it_edi_doi_declaration_of_intent_id = fields.Many2one(
        comodel_name='l10n_it_edi_doi.declaration_of_intent',
        compute='_compute_l10n_it_edi_doi_declaration_of_intent_id',
        store=True,
        string="Declaration of Intent Tax",
    )

    @api.depends('company_id', 'move_id', 'move_id.l10n_it_edi_doi_declaration_of_intent_id', 'tax_ids')
    def _compute_l10n_it_edi_doi_declaration_of_intent_id(self):
        declaration_lines = self.filtered(
            lambda line: (line.move_id.l10n_it_edi_doi_declaration_of_intent_id
                          and line.company_id.l10n_it_edi_doi_declaration_of_intent_tax
                          # The declaration tax cannot be used with other taxes on a single line
                          # (checked in `_post` of model 'account.move')
                          and line.tax_ids.ids == line.company_id.l10n_it_edi_doi_declaration_of_intent_tax.ids)
        )
        for line in declaration_lines:
            declaration = line.move_id.l10n_it_edi_doi_declaration_of_intent_id
            line.l10n_it_edi_doi_declaration_of_intent_id = declaration
        (self - declaration_lines).l10n_it_edi_doi_declaration_of_intent_id = False

    def _l10n_it_edi_doi_sum_signed_amount(self):
        """
        This function returns the sum of the signed price_total of all lines.
        The move_type of the individual lines determines the sign.
        """
        amount = 0
        for move_type, lines in self.grouped('move_type').items():
            sign = 1 if move_type in self.env['account.move'].get_inbound_types(include_receipts=True) else -1
            amount += sign * sum(lines.mapped('price_total'))
        return amount
