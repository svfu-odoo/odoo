# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_it_declaration_of_intent_date = fields.Date(
        string="Date on which Declaration of Intent is applied",
        compute='_compute_l10n_it_declaration_of_intent_date',
    )

    l10n_it_use_declaration_of_intent = fields.Boolean(
        string="Use Declaration of Intent",
        compute='_compute_l10n_it_use_declaration_of_intent',
    )

    l10n_it_declaration_of_intent_id = fields.Many2one(
        string="Declaration of Intent",
        compute='_compute_l10n_it_declaration_of_intent_id',
        store=True, readonly=False, precompute=True,
        comodel_name='l10n_it.declaration_of_intent',
    )

    l10n_it_intent_threshold_warning = fields.Text(
        string="Declaration of Intent Threshold Warning",
        compute='_compute_l10n_it_intent_threshold_warning',
    )

    @api.depends('invoice_date')
    def _compute_l10n_it_declaration_of_intent_date(self):
        for move in self:
            move.l10n_it_declaration_of_intent_date = move.invoice_date or fields.Date.context_today(self)

    @api.depends('l10n_it_declaration_of_intent_id', 'commercial_partner_id')
    def _compute_l10n_it_use_declaration_of_intent(self):
        for move in self:
            move.l10n_it_use_declaration_of_intent = move.l10n_it_declaration_of_intent_id \
                or move.commercial_partner_id.l10n_it_is_regular_exporter

    @api.depends('company_id', 'partner_id', 'l10n_it_declaration_of_intent_date', 'currency_id')
    def _compute_l10n_it_declaration_of_intent_id(self):
        for move in self:
            if not move.l10n_it_use_declaration_of_intent:
                move.l10n_it_declaration_of_intent_id = False
                continue

            company = move.company_id
            partner = move.partner_id.commercial_partner_id
            date = move.l10n_it_declaration_of_intent_date
            currency = move.currency_id

            # Avoid a query or changing a manually set declaration of intent
            # (if the declaration is still valid).
            current_declaration = move.l10n_it_declaration_of_intent_id
            if current_declaration and current_declaration._is_valid(company, partner, date, currency):
                continue

            declaration = self.env['l10n_it.declaration_of_intent']\
                ._fetch_valid_declaration_of_intent(company, partner, date, currency)
            move.l10n_it_declaration_of_intent_id = declaration

    @api.depends('l10n_it_declaration_of_intent_id', 'move_type', 'state', 'tax_totals')
    def _compute_l10n_it_intent_threshold_warning(self):
        for move in self:
            move.l10n_it_intent_threshold_warning = ''
            declaration = move.l10n_it_declaration_of_intent_id

            show_warning = declaration \
                and move.is_sale_document() \
                and move.state != 'cancel'
            if not show_warning:
                continue

            updated_remaining = declaration.remaining_amount
            if move.state != 'posted':  # exactly the 'posted' invoices are included in declaration.consumed_amount
                updated_remaining -= move.tax_totals['amount_total']
            move.l10n_it_intent_threshold_warning = declaration._build_threshold_warning_message(move, updated_remaining)

    @api.depends('l10n_it_declaration_of_intent_id')
    def _compute_fiscal_position_id(self):
        super()._compute_fiscal_position_id()
        for move in self:
            if move.l10n_it_declaration_of_intent_id:
                declaration_fiscal_position = move.company_id._l10n_it_get_declaration_of_intent_fiscal_position()
                if declaration_fiscal_position:
                    move.fiscal_position_id = declaration_fiscal_position

    def _post(self, soft=True):
        records_with_declaration = self.filtered(lambda record: record.l10n_it_declaration_of_intent_id)
        for record in records_with_declaration:
            if not record.currency_id.is_zero(record.amount_tax):
                raise UserError(_('Invoices using a Declaration of Intent should have a 0 tax amount.'))
        records_without_declaration = (self - records_with_declaration)
        for record in records_without_declaration:
            declaration_of_intent_tax = record.company_id._l10n_it_get_declaration_of_intent_tax()
            if declaration_of_intent_tax and declaration_of_intent_tax in record.mapped('invoice_line_ids.tax_ids'):
                raise UserError(_('Given the tax %s is applied, there should be a Declaration of Intent selected.',
                                  declaration_of_intent_tax.name))
        return super()._post(soft)

    @api.constrains('l10n_it_declaration_of_intent_id')
    def _check_l10n_it_declaration_of_intent_id(self):
        for move in self:
            declaration = move.l10n_it_declaration_of_intent_id
            if not declaration:
                return
            partner = move.commercial_partner_id
            date = move.l10n_it_declaration_of_intent_date
            declaration._check_valid(move.company_id, partner, date, move.currency_id)

    def action_open_declaration_of_intent(self):
        self.ensure_one()
        return {
            'name': _("Declaration of Intent for %s", self.display_name),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'l10n_it.declaration_of_intent',
            'res_id': self.l10n_it_declaration_of_intent_id.id,
        }
