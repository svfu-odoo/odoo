# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_it_edi_doi_declaration_of_intent_date = fields.Date(
        string="Date on which Declaration of Intent is applied",
        compute='_compute_l10n_it_edi_doi_declaration_of_intent_date',
    )

    l10n_it_edi_doi_use_declaration_of_intent = fields.Boolean(
        string="Use Declaration of Intent",
        compute='_compute_l10n_it_edi_doi_use_declaration_of_intent',
    )

    l10n_it_edi_doi_declaration_of_intent_id = fields.Many2one(
        string="Declaration of Intent",
        compute='_compute_l10n_it_edi_doi_declaration_of_intent_id',
        store=True, readonly=False, precompute=True,
        comodel_name='l10n_it_edi_doi.declaration_of_intent',
    )

    l10n_it_edi_doi_warning = fields.Text(
        string="Declaration of Intent Threshold Warning",
        compute='_compute_l10n_it_edi_doi_warning',
    )

    @api.depends('invoice_date')
    def _compute_l10n_it_edi_doi_declaration_of_intent_date(self):
        for move in self:
            move.l10n_it_edi_doi_declaration_of_intent_date = move.invoice_date or fields.Date.context_today(self)

    @api.depends('l10n_it_edi_doi_declaration_of_intent_id', 'commercial_partner_id')
    def _compute_l10n_it_edi_doi_use_declaration_of_intent(self):
        for move in self:
            move.l10n_it_edi_doi_use_declaration_of_intent = move.l10n_it_edi_doi_declaration_of_intent_id \
                or move.commercial_partner_id.l10n_it_edi_doi_is_regular_exporter

    @api.depends('company_id', 'partner_id', 'l10n_it_edi_doi_declaration_of_intent_date', 'currency_id')
    def _compute_l10n_it_edi_doi_declaration_of_intent_id(self):
        for move in self:
            if move.state != 'draft' or not move.l10n_it_edi_doi_use_declaration_of_intent:
                move.l10n_it_edi_doi_declaration_of_intent_id = False
                continue

            company = move.company_id
            partner = move.partner_id.commercial_partner_id
            date = move.l10n_it_edi_doi_declaration_of_intent_date
            currency = move.currency_id

            # Avoid a query or changing a manually set declaration of intent
            # (if the declaration is still valid).
            current_declaration = move.l10n_it_edi_doi_declaration_of_intent_id
            if current_declaration and not current_declaration._get_validity_warnings(company, partner, currency, date):
                continue

            declaration = self.env['l10n_it_edi_doi.declaration_of_intent']\
                ._fetch_valid_declaration_of_intent(company, partner, currency, date)
            move.l10n_it_edi_doi_declaration_of_intent_id = declaration

    @api.depends('l10n_it_edi_doi_declaration_of_intent_id', 'move_type', 'state', 'tax_totals')
    def _compute_l10n_it_edi_doi_warning(self):
        for move in self:
            move.l10n_it_edi_doi_warning = ''
            declaration = move.l10n_it_edi_doi_declaration_of_intent_id

            show_warning = declaration \
                and move.is_sale_document(include_receipts=False) \
                and move.state != 'cancel'
            if not show_warning:
                continue

            declaration_invoiced = declaration.invoiced
            declaration_not_yet_invoiced = declaration.not_yet_invoiced
            if move.state != 'posted':  # exactly the 'posted' invoice lines are included in declaration.invoiced
                # Here we replicate what would happen when posting the invoice
                #   * `declaration.invoiced` will increase by the invoiced amount
                #   * `declaration.not_yet_invoiced` will decrease by the now invoiced sale order amount (see computation below)
                # Note: lines manually added to a invoice or credit note linked to sales order are not added to the sales order

                declaration_lines = move.invoice_line_ids.filtered(
                    lambda line: line.l10n_it_edi_doi_declaration_of_intent_id == declaration
                )
                declaration_invoiced += declaration_lines._l10n_it_edi_doi_sum_signed_amount()

                relevant_sale_lines = declaration_lines.sale_line_ids.filtered(
                    lambda line: line.l10n_it_edi_doi_declaration_of_intent_id == declaration
                                 and line.order_id.state == 'sale'
                )
                not_yet_invoiced_now = relevant_sale_lines._l10n_it_edi_doi_get_amount_not_yet_invoiced()
                not_yet_invoiced_after_posting = relevant_sale_lines._l10n_it_edi_doi_get_amount_not_yet_invoiced(
                    unposted_invoice_lines=declaration_lines
                )
                declaration_not_yet_invoiced -= not_yet_invoiced_now - not_yet_invoiced_after_posting

            validity_warnings = move._l10n_it_edi_doi_get_declaration_of_intent_validity_warnings()

            move.l10n_it_edi_doi_warning = '{}\n\n{}'.format(
                '\n'.join(validity_warnings),
                declaration._build_threshold_warning_message(declaration_invoiced, declaration_not_yet_invoiced),
            ).strip()

    @api.depends('l10n_it_edi_doi_declaration_of_intent_id')
    def _compute_fiscal_position_id(self):
        super()._compute_fiscal_position_id()
        for company_id, moves in self.grouped('company_id').items():
            declaration_fiscal_position = company_id._l10n_it_edi_doi_get_declaration_of_intent_fiscal_position()
            if not declaration_fiscal_position:
                continue
            for move in moves:
                if move.l10n_it_edi_doi_declaration_of_intent_id:
                    move.fiscal_position_id = declaration_fiscal_position

    def copy_data(self, default=None):
        data_list = super().copy_data(default)
        for move, data in zip(self, data_list):
            declaration = move.l10n_it_edi_doi_declaration_of_intent_id
            date = fields.Date.context_today(self)
            if declaration._get_validity_warnings(move.company_id, move.partner_id, move.currency_id, date):
                del data['l10n_it_edi_doi_declaration_of_intent_id']
                del data['fiscal_position_id']
        return data_list

    def _l10n_it_edi_doi_get_declaration_of_intent_validity_warnings(self, only_blocking=False):
        self.ensure_one()
        declaration = self.l10n_it_edi_doi_declaration_of_intent_id
        if not declaration:
            return []
        partner = self.commercial_partner_id
        date = self.l10n_it_edi_doi_declaration_of_intent_date
        declaration_lines = self.invoice_line_ids.filtered(
            lambda line: line.l10n_it_edi_doi_declaration_of_intent_id
        )
        invoiced_amount = declaration_lines._l10n_it_edi_doi_sum_signed_amount()
        return declaration._get_validity_warnings(
            self.company_id, partner, self.currency_id, date,
            invoiced_amount=invoiced_amount, only_blocking=only_blocking
        )

    @api.constrains('l10n_it_edi_doi_declaration_of_intent_id')
    def _check_l10n_it_edi_doi_declaration_of_intent_id(self):
        for move in self:
            declaration = move.l10n_it_edi_doi_declaration_of_intent_id
            if not declaration:
                return
            validity_errors = declaration._get_validity_errors(
                move.company_id, move.partner_id, move.currency_id
            )
            if validity_errors:
                raise UserError('\n'.join(validity_errors))

    def _post(self, soft=True):
        errors = []
        for company_id, records in self.grouped('company_id').items():
            declaration_of_intent_tax = company_id.l10n_it_edi_doi_declaration_of_intent_tax
            if not declaration_of_intent_tax:
                continue
            for move in records:
                validity_warnings = move._l10n_it_edi_doi_get_declaration_of_intent_validity_warnings(only_blocking=True)
                errors.extend(validity_warnings)

                declaration_tax_lines = move.invoice_line_ids.filtered(
                    lambda line: declaration_of_intent_tax in line.tax_ids
                   )
                for line in declaration_tax_lines:
                    if not line.l10n_it_edi_doi_declaration_of_intent_id:
                        errors.append(_('Given the tax %s is applied, there should be a Declaration of Intent selected.',
                                        declaration_of_intent_tax.name))
                    if line.tax_ids != declaration_of_intent_tax:
                        errors.append(_('A line using tax %s should not contain any other taxes',
                                        declaration_of_intent_tax.name))
        if errors:
            raise UserError('\n'.join(errors))

        return super()._post(soft)

    def action_open_declaration_of_intent(self):
        self.ensure_one()
        return {
            'name': _("Declaration of Intent for %s", self.display_name),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'l10n_it_edi_doi.declaration_of_intent',
            'res_id': self.l10n_it_edi_doi_declaration_of_intent_id.id,
        }
