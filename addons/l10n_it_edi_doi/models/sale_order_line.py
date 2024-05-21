# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    l10n_it_edi_doi_declaration_of_intent_id = fields.Many2one(
        comodel_name='l10n_it_edi_doi.declaration_of_intent',
        compute='_compute_l10n_it_edi_doi_declaration_of_intent_id',
        store=True,
        string="Declaration of Intent Tax",
    )

    @api.depends('company_id', 'order_id', 'order_id.l10n_it_edi_doi_declaration_of_intent_id', 'tax_id')
    def _compute_l10n_it_edi_doi_declaration_of_intent_id(self):
        declaration_lines = self.filtered(
            lambda line: (line.order_id.l10n_it_edi_doi_declaration_of_intent_id
                          and line.company_id.l10n_it_edi_doi_declaration_of_intent_tax
                          # The declaration tax cannot be used with other taxes on a single line
                          # (checked in `_post` of model 'account.move')
                          and line.tax_id.ids == line.company_id.l10n_it_edi_doi_declaration_of_intent_tax.ids)
        )
        for line in declaration_lines:
            declaration = line.order_id.l10n_it_edi_doi_declaration_of_intent_id
            line.l10n_it_edi_doi_declaration_of_intent_id = declaration
        (self - declaration_lines).l10n_it_edi_doi_declaration_of_intent_id = False

    def _l10n_it_edi_doi_get_amount_not_yet_invoiced(self, unposted_invoice_lines=None):
        """
        For each line in `self` that belongs to a declaration we compute the amount that is not yet invoiced
        (by a posted invoice line belonging to the same declaration).
        The returned result is the sum of all those not yet invoiced amounts.
        We also consider lines whose sale order is not confirmed yet (still a quotation).
        :param dict unposted_invoice_lines: A recordset of 'account.move.line'.
                                            These lines will be considered even if they are not posted yet.
                                            This can i.e. be used to simulate posting an invoice.
        """
        if not unposted_invoice_lines:
            unposted_invoice_lines = self.env['account.move.line']

        total_not_yet_invoiced = 0
        for line in self:
            declaration = line.l10n_it_edi_doi_declaration_of_intent_id
            if not declaration:
                continue
            to_invoice = line.price_total
            invoice_lines = line._get_invoice_lines().filtered(
                lambda invoice_line: invoice_line.l10n_it_edi_doi_declaration_of_intent_id == declaration
                                     and (invoice_line.move_id.state == 'posted'
                                          or invoice_line in unposted_invoice_lines)
            )
            # TODO: can to_invoice be negative? Does it make a difference?
            not_yet_invoiced = to_invoice - invoice_lines._l10n_it_edi_doi_sum_signed_amount()
            if not_yet_invoiced > 0:
                total_not_yet_invoiced += max(to_invoice, not_yet_invoiced)
        return total_not_yet_invoiced
