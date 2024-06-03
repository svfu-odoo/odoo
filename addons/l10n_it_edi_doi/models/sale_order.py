# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

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

    l10n_it_edi_doi_not_yet_invoiced = fields.Monetary(
        string='Declaration of Intent Amount Not Yet Invoiced',
        compute='_compute_l10n_it_edi_doi_not_yet_invoiced',
        store=True, readonly=True,
        help="Total under the Declaration of Intent of this document that can still be invoiced",
    )

    l10n_it_edi_doi_warning = fields.Text(
        string="Declaration of Intent Threshold Warning",
        compute='_compute_l10n_it_edi_doi_warning',
    )

    @api.depends('commitment_date')
    def _compute_l10n_it_edi_doi_declaration_of_intent_date(self):
        for order in self:
            order.l10n_it_edi_doi_declaration_of_intent_date = order.commitment_date or fields.Date.context_today(self)

    @api.depends('l10n_it_edi_doi_declaration_of_intent_id',
                 'country_code',
                 'partner_id.commercial_partner_id.l10n_it_edi_doi_is_regular_exporter')
    def _compute_l10n_it_edi_doi_use_declaration_of_intent(self):
        for order in self:
            order.l10n_it_edi_doi_use_declaration_of_intent = order.l10n_it_edi_doi_declaration_of_intent_id \
                or ("IT" in order.country_code and order.partner_id.commercial_partner_id.l10n_it_edi_doi_is_regular_exporter)

    @api.depends('company_id', 'partner_id.commercial_partner_id', 'l10n_it_edi_doi_declaration_of_intent_date', 'currency_id')
    def _compute_l10n_it_edi_doi_declaration_of_intent_id(self):
        for order in self:
            if order.state != 'draft' or not order.l10n_it_edi_doi_use_declaration_of_intent:
                order.l10n_it_edi_doi_declaration_of_intent_id = False
                continue

            company = order.company_id
            partner = order.partner_id.commercial_partner_id
            date = order.l10n_it_edi_doi_declaration_of_intent_date
            currency = order.currency_id

            # Avoid a query or changing a manually set declaration of intent
            # (if the declaration is still valid).
            current_declaration = order.l10n_it_edi_doi_declaration_of_intent_id
            if current_declaration and not current_declaration._get_validity_warnings(company, partner, currency, date):
                continue

            declaration = self.env['l10n_it_edi_doi.declaration_of_intent']\
                ._fetch_valid_declaration_of_intent(company, partner, currency, date)
            order.l10n_it_edi_doi_declaration_of_intent_id = declaration

    @api.depends('tax_totals', 'invoice_ids', 'invoice_ids.state', 'invoice_ids.tax_totals')
    def _compute_l10n_it_edi_doi_not_yet_invoiced(self):
        for order in self:
            declaration = order.l10n_it_edi_doi_declaration_of_intent_id
            order.l10n_it_edi_doi_not_yet_invoiced = order._l10n_it_edi_doi_get_amount_not_yet_invoiced(declaration)

    @api.depends('l10n_it_edi_doi_declaration_of_intent_id', 'l10n_it_edi_doi_declaration_of_intent_id.remaining', 'state', 'tax_totals')
    def _compute_l10n_it_edi_doi_warning(self):
        for order in self:
            order.l10n_it_edi_doi_warning = ''
            declaration = order.l10n_it_edi_doi_declaration_of_intent_id

            show_warning = declaration and order.state != 'cancelled'
            if not show_warning:
                continue

            declaration_invoiced = declaration.invoiced
            declaration_not_yet_invoiced = declaration.not_yet_invoiced
            if order.state == 'sale':
                # Exactly the 'sale' invoices are included in declaration.not_yet_invoiced
                old_order_state = self.browse(order.ids)
                declaration_not_yet_invoiced -= old_order_state.l10n_it_edi_doi_not_yet_invoiced
            declaration_not_yet_invoiced += order._l10n_it_edi_doi_get_amount_not_yet_invoiced(declaration)

            date = order.l10n_it_edi_doi_declaration_of_intent_date
            validity_warnings = declaration._get_validity_warnings(
                order.company_id, order.partner_id.commercial_partner_id, order.currency_id, date
            )

            order.l10n_it_edi_doi_warning = '{}\n\n{}'.format(
                '\n'.join(validity_warnings),
                declaration._build_threshold_warning_message(declaration_invoiced, declaration_not_yet_invoiced),
            ).strip()

    @api.depends('l10n_it_edi_doi_declaration_of_intent_id')
    def _compute_fiscal_position_id(self):
        super()._compute_fiscal_position_id()
        for company_id, orders in self.grouped('company_id').items():
            declaration_fiscal_position = company_id.l10n_it_edi_doi_declaration_of_intent_fiscal_position
            if not declaration_fiscal_position:
                continue
            for order in orders:
                if order.l10n_it_edi_doi_declaration_of_intent_id:
                    order.fiscal_position_id = declaration_fiscal_position

    def _prepare_invoice(self):
        """
        Prepare the dict of values to create the new invoice for a sales order. This method may be
        overridden to implement custom invoice generation (making sure to call super() to establish
        a clean extension chain).
        """
        vals = super()._prepare_invoice()
        declaration = self.l10n_it_edi_doi_declaration_of_intent_id
        if declaration:
            company = self.env['res.company'].browse(vals['company_id'])
            partner = self.env['res.partner'].browse(vals['partner_id']).commercial_partner_id
            date = fields.Date.context_today(self)
            currency = self.env['res.currency'].browse(vals['currency_id'])
            if not declaration._get_validity_warnings(company, partner, currency, date):
                vals['l10n_it_edi_doi_declaration_of_intent_id'] = declaration.id
        return vals

    def copy_data(self, default=None):
        data_list = super().copy_data(default)
        for order, data in zip(self, data_list):
            declaration = order.l10n_it_edi_doi_declaration_of_intent_id
            date = fields.Date.context_today(self)
            if declaration._get_validity_warnings(order.company_id, order.partner_id.commercial_partner_id, order.currency_id, date):
                del data['l10n_it_edi_doi_declaration_of_intent_id']
                del data['fiscal_position_id']
        return data_list

    def _l10n_it_edi_doi_check_configuration(self):
        """
        Raise a UserError in case the configuration of the sale order is invalid.
        """
        for company_id, records in self.grouped('company_id').items():
            declaration_of_intent_tax = company_id.l10n_it_edi_doi_declaration_of_intent_tax
            if not declaration_of_intent_tax:
                continue
            declaration_tax_lines = records.order_line.filtered(
                lambda line: declaration_of_intent_tax in line.tax_id
            )
            for line in declaration_tax_lines:
                if not line.order_id.l10n_it_edi_doi_declaration_of_intent_id:
                    raise UserError(_('Given the tax %s is applied, there should be a Declaration of Intent selected.',
                                      declaration_of_intent_tax.name))
                if line.tax_id != declaration_of_intent_tax:
                    raise UserError(_('A line using tax %s should not contain any other taxes',
                                      declaration_of_intent_tax.name))

    def action_quotation_send(self):
        self._l10n_it_edi_doi_check_configuration()
        return super().action_quotation_send()

    def action_quotation_sent(self):
        self._l10n_it_edi_doi_check_configuration()
        return super().action_quotation_sent()

    def action_confirm(self):
        self._l10n_it_edi_doi_check_configuration()
        return super().action_confirm()

    @api.constrains('l10n_it_edi_doi_declaration_of_intent_id')
    def _check_l10n_it_edi_doi_declaration_of_intent_id(self):
        for order in self:
            declaration = order.l10n_it_edi_doi_declaration_of_intent_id
            if not declaration:
                return
            partner = order.partner_id.commercial_partner_id
            date = order.l10n_it_edi_doi_declaration_of_intent_date
            errors = declaration._get_validity_warnings(
                order.company_id, partner, order.currency_id, date, only_blocking=True
            )
            if errors:
                raise ValidationError('\n'.join(errors))

    def action_open_declaration_of_intent(self):
        self.ensure_one()
        return {
            'name': _("Declaration of Intent for %s", self.display_name),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'l10n_it_edi_doi.declaration_of_intent',
            'res_id': self.l10n_it_edi_doi_declaration_of_intent_id.id,
        }

    def _l10n_it_edi_doi_get_amount_not_yet_invoiced(self, declaration, additional_invoiced_qty={}):
        """
        Consider sales orders in self that use declaration of intent `declaration`.
        For each sales order we compute the amount that is tax exempt due to the declaration of intent
        (line has special declaration of intent tax applied) but not yet invoiced.
        For each line of the SO we i.e. use the not yet invoiced quantity to compute this amount.
        The aforementioned quantity is computed from field `qty_invoiced_posted` and parameter `additional_invoiced_qty`
        Return the sum of all these amounts on the SOs.
        :param declaration:             We only consider sales orders using Declaration of Intent `declaration`.
        :param additional_invoiced_qty: Dictionary (sale order line id -> float)
                                        The float represents additional invoiced amount qty for the sale order.
                                        This can i.e. be used to simulate posting an already linked invoice.
        """
        if not declaration:
            return 0

        tax = declaration.company_id.l10n_it_edi_doi_declaration_of_intent_tax
        if not tax:
            return 0

        not_yet_invoiced = 0
        for order in self:
            declaration = order.l10n_it_edi_doi_declaration_of_intent_id
            if not declaration:
                continue

            order_lines = order.order_line.filtered(
                # The declaration tax cannot be used with other taxes on a single line
                # (checked in `action_confirm`)
                lambda line: line.tax_id.ids == tax.ids
            )
            order_not_yet_invoiced = 0
            for line in order_lines:
                price_reduce = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
                qty_invoiced = line.qty_invoiced_posted + additional_invoiced_qty.get(line.id, 0)
                qty_to_invoice = line.product_uom_qty - qty_invoiced
                order_not_yet_invoiced += price_reduce * qty_to_invoice
            if order_not_yet_invoiced > 0:
                not_yet_invoiced += order_not_yet_invoiced

        return not_yet_invoiced
