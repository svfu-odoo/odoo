# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class L10nItDeclarationOfIntent(models.Model):
    _inherit = 'l10n_it.declaration_of_intent'

    sale_order_ids = fields.One2many(
        'sale.order',
        'l10n_it_declaration_of_intent_id',
        string="Sales Orders / Quotations",
      copy=False,
      readonly=True,
    )

    @api.depends('sale_order_ids', 'sale_order_ids.state', 'sale_order_ids.amount_to_invoice')
    def _compute_committed_amount(self):
        # override method from l10n_it
        super()._compute_committed_amount()
        if not self.ids:
            return
        domain = [
            ('l10n_it_declaration_of_intent_id', 'in', self.ids),
            ('state', '=', 'sale'),
        ]
        group = self.env['sale.order']._read_group(domain, ['l10n_it_declaration_of_intent_id'], ['amount_to_invoice:sum'])
        treated = self.env[self._name]
        for declaration, amount_to_invoice_sum in group:
            declaration.committed_amount += amount_to_invoice_sum
            treated |= declaration
        (self - treated).committed_amount = False

    @api.ondelete(at_uninstall=False)
    def _unlink_except_linked_to_sale_order(self):
        if self.env['sale.order'].search_count([('l10n_it_declaration_of_intent_id', 'in', self.ids)], limit=1):
            raise UserError(_('You cannot delete the Declarations of Intent "%s". At least one of them is used on a Sales Order already.', ', '.join(d.display_name for d in self)))
