# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.addons.account.models.account_move import PAYMENT_STATE_SELECTION

from functools import lru_cache


class AccountInvoiceReport(models.Model):
    _name = "account.invoice.report"
    _description = "Invoices Statistics"
    _auto = False
    _rec_name = 'invoice_date'
    _order = 'invoice_date desc'

    # ==== Invoice fields ====
    move_id = fields.Many2one('account.move', readonly=True)
    journal_id = fields.Many2one('account.journal', string='Journal', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    company_currency_id = fields.Many2one('res.currency', string='Company Currency', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
    commercial_partner_id = fields.Many2one('res.partner', string='Main Partner')
    country_id = fields.Many2one('res.country', string="Country")
    invoice_user_id = fields.Many2one('res.users', string='Salesperson', readonly=True)
    move_type = fields.Selection([
        ('out_invoice', 'Customer Invoice'),
        ('in_invoice', 'Vendor Bill'),
        ('out_refund', 'Customer Credit Note'),
        ('in_refund', 'Vendor Credit Note'),
        ], readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Open'),
        ('cancel', 'Cancelled')
        ], string='Invoice Status', readonly=True)
    payment_state = fields.Selection(selection=PAYMENT_STATE_SELECTION, string='Payment Status', readonly=True)
    fiscal_position_id = fields.Many2one('account.fiscal.position', string='Fiscal Position', readonly=True)
    invoice_date = fields.Date(readonly=True, string="Invoice Date")

    # ==== Invoice line fields ====
    quantity = fields.Float(string='Product Quantity', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure', readonly=True)
    product_categ_id = fields.Many2one('product.category', string='Product Category', readonly=True)
    invoice_date_due = fields.Date(string='Due Date', readonly=True)
    account_id = fields.Many2one('account.account', string='Revenue/Expense Account', readonly=True, domain=[('deprecated', '=', False)])
    price_subtotal = fields.Float(string='Untaxed Total', readonly=True)
    balance2 = fields.Float(string='Untaxed Total 2', readonly=True)
    price_total = fields.Float(string='Total', readonly=True)
    price_total_company = fields.Float(string='Total Company Currency', readonly=True)
    price_total_company2 = fields.Float(string='Total Company Currency 2', readonly=True)
    price_total_hacky = fields.Float(string='Total Company Currency (hacky)', readonly=True)
    price_average = fields.Float(string='Average Price', readonly=True, group_operator="avg")

    _depends = {
        'account.move': [
            'name', 'state', 'move_type', 'partner_id', 'invoice_user_id', 'fiscal_position_id',
            'invoice_date', 'invoice_date_due', 'invoice_payment_term_id', 'partner_bank_id',
        ],
        'account.move.line': [
            'quantity', 'price_subtotal', 'price_total', 'amount_residual', 'balance', 'amount_currency',
            'move_id', 'product_id', 'product_uom_id', 'account_id',
            'journal_id', 'company_id', 'currency_id', 'partner_id',
        ],
        'product.product': ['product_tmpl_id'],
        'product.template': ['categ_id'],
        'uom.uom': ['category_id', 'factor', 'name', 'uom_type'],
        'res.currency.rate': ['currency_id', 'name'],
        'res.partner': ['country_id'],
    }

    @property
    def _table_query(self):
        return '%s %s %s %s' % (self._with(), self._select(), self._from(), self._where())

    @api.model
    def _with(self):
        return f'''
            WITH company_currencies AS ({self.env['res.currency']._select_companies_rates()})
        '''

    @api.model
    def _select(self):
        return '''
            SELECT
                line.id,
                line.move_id,
                line.product_id,
                line.account_id,
                line.journal_id,
                line.company_id,
                line.company_currency_id,
                line.currency_id,
                line.partner_id AS commercial_partner_id,
                account.account_type AS user_type,
                move.state,
                move.move_type,
                move.partner_id,
                move.invoice_user_id,
                move.fiscal_position_id,
                move.payment_state,
                move.invoice_date,
                move.invoice_date_due,
                uom_template.id                                             AS product_uom_id,
                template.categ_id                                           AS product_categ_id,
                line.quantity / NULLIF(COALESCE(uom_line.factor, 1) / COALESCE(uom_template.factor, 1), 0.0) * (CASE WHEN move.move_type IN ('in_invoice','out_refund','in_receipt') THEN -1 ELSE 1 END)
                                                                            AS quantity,
                -line.balance * currency_table.rate                         AS price_subtotal,
                line.price_total * (CASE WHEN move.move_type IN ('in_invoice','out_refund','in_receipt') THEN -1 ELSE 1 END)
                                                                            AS price_total,
                -- choose rate 1.0 in case we are at time before first entered rate for company / currency combo
                COALESCE(line_currency_conversion.rate,1.0)
                                                                            AS line_rate,
                COALESCE(company_currency_conversion.rate,1.0)
                                                                            AS company_rate,
                ROUND(line.price_subtotal
                          * COALESCE(company_currency_conversion.rate, 1.0)
                          / COALESCE(line_currency_conversion.rate, 1.0)
                      , company_currency.decimal_places)
                    * (CASE WHEN move.move_type IN ('in_invoice','out_refund','in_receipt') THEN -1 ELSE 1 END)
                    * currency_table.rate
                                                                            AS balance2,
                ROUND(line.price_total
                          * COALESCE(company_currency_conversion.rate, 1.0)
                          / COALESCE(line_currency_conversion.rate, 1.0)
                      , company_currency.decimal_places)
                    * currency_table.rate
                                                                            AS price_total_company,
                CASE line.price_subtotal
                    WHEN 0
                        THEN 0
                        ELSE ROUND(line.price_total * ABS(line.balance / line.price_subtotal), company_currency.decimal_places)
                    END
                    * currency_table.rate
                                                                            AS price_total_hacky,
                amls_company_currency.price_total * (CASE WHEN move.move_type IN ('in_invoice','out_refund','in_receipt') THEN -1 ELSE 1 END) * currency_table.rate
                                                                            AS price_total_company2,
                -COALESCE(
                   -- Average line price
                   (line.balance / NULLIF(line.quantity, 0.0)) * (CASE WHEN move.move_type IN ('in_invoice','out_refund','in_receipt') THEN -1 ELSE 1 END)
                   -- convert to template uom
                   * (NULLIF(COALESCE(uom_line.factor, 1), 0.0) / NULLIF(COALESCE(uom_template.factor, 1), 0.0)),
                   0.0) * currency_table.rate                               AS price_average,
                COALESCE(partner.country_id, commercial_partner.country_id) AS country_id
        '''

    @api.model
    def _from(self):
        amls = self.env['account.move.line'].search([])
        query_template = '(VALUES %s) AS amls_company_currency(line_id, price_total)' % ','.join('(%s, %s)' for _line in amls)
        amls_company_currency_values = []
        for line in amls:
            amls_company_currency_values.extend((
                line.id,
                line.company_currency_id.round(line.price_total / line.currency_rate),
            ))
        amls_company_currency = self.env.cr.mogrify(query_template, amls_company_currency_values).decode(self.env.cr.connection.encoding)
        return '''
            FROM account_move_line line
                LEFT JOIN res_partner partner ON partner.id = line.partner_id
                LEFT JOIN product_product product ON product.id = line.product_id
                LEFT JOIN account_account account ON account.id = line.account_id
                LEFT JOIN product_template template ON template.id = product.product_tmpl_id
                LEFT JOIN uom_uom uom_line ON uom_line.id = line.product_uom_id
                LEFT JOIN uom_uom uom_template ON uom_template.id = template.uom_id
                INNER JOIN account_move move ON move.id = line.move_id
                LEFT JOIN res_partner commercial_partner ON commercial_partner.id = move.commercial_partner_id
                JOIN {currency_table} ON currency_table.company_id = line.company_id
                LEFT JOIN company_currencies line_currency_conversion ON
                      line.currency_id = line_currency_conversion.currency_id
                  AND line.company_id = line_currency_conversion.company_id
                  AND COALESCE(line.date, NOW()) >= line_currency_conversion.date_start
                  AND (line_currency_conversion.date_end IS NULL OR line_currency_conversion.date_end > COALESCE(line.date, NOW()))
                LEFT JOIN company_currencies company_currency_conversion ON
                      line.company_currency_id = company_currency_conversion.currency_id
                  AND line.company_id = company_currency_conversion.company_id
                  AND COALESCE(line.date, NOW()) >= company_currency_conversion.date_start
                  AND (company_currency_conversion.date_end IS NULL OR company_currency_conversion.date_end > COALESCE(line.date, NOW()))
                LEFT JOIN res_currency company_currency ON company_currency.id = line.company_currency_id
                LEFT JOIN {amls_company_currency} ON amls_company_currency.line_id = line.id
        '''.format(
            currency_table=self.env['res.currency']._get_query_currency_table({'multi_company': True, 'date': {'date_to': fields.Date.today()}}),
            amls_company_currency=amls_company_currency,
        )

    @api.model
    def _where(self):
        return '''
            WHERE move.move_type IN ('out_invoice', 'out_refund', 'in_invoice', 'in_refund', 'out_receipt', 'in_receipt')
                AND line.account_id IS NOT NULL
                AND line.display_type = 'product'
        '''


class ReportInvoiceWithoutPayment(models.AbstractModel):
    _name = 'report.account.report_invoice'
    _description = 'Account report without payment lines'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['account.move'].browse(docids)

        qr_code_urls = {}
        for invoice in docs:
            if invoice.display_qr_code:
                new_code_url = invoice._generate_qr_code(silent_errors=data['report_type'] == 'html')
                if new_code_url:
                    qr_code_urls[invoice.id] = new_code_url

        return {
            'doc_ids': docids,
            'doc_model': 'account.move',
            'docs': docs,
            'qr_code_urls': qr_code_urls,
        }

class ReportInvoiceWithPayment(models.AbstractModel):
    _name = 'report.account.report_invoice_with_payments'
    _description = 'Account report with payment lines'
    _inherit = 'report.account.report_invoice'

    @api.model
    def _get_report_values(self, docids, data=None):
        rslt = super()._get_report_values(docids, data)
        rslt['report_type'] = data.get('report_type') if data else ''
        return rslt
