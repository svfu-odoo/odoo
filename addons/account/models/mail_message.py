# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.osv.expression import OR

bypass_token = object()
# MODEL_FIELD maps each supported model to the field through which it can be accessed.
# Each supported model has to have a searchable field `check_account_audit_trail`.
MODEL_FIELD = {
    'account.move': 'account_audit_log_move_id',
    'account.account': 'account_audit_log_account_id',
    'account.tax': 'account_audit_log_tax_id',
    'res.partner': 'account_audit_log_partner_id',
    'res.company': 'account_audit_log_company_id',
}


class Message(models.Model):
    _inherit = 'mail.message'

    account_audit_log_preview = fields.Text(string="Description", compute="_compute_account_audit_log_preview")
    account_audit_log_move_id = fields.Many2one(
        comodel_name='account.move',
        string="Journal Entry",
        compute="_compute_audit_log_related_record_id",
        search="_search_account_audit_log_move_id",
    )
    account_audit_log_partner_id = fields.Many2one(
        comodel_name='res.partner',
        string="Partner",
        compute="_compute_audit_log_related_record_id",
        search="_search_account_audit_log_partner_id",
    )
    account_audit_log_account_id = fields.Many2one(
        comodel_name='account.account',
        string="Account",
        compute="_compute_audit_log_related_record_id",
        search="_search_account_audit_log_account_id",
    )
    account_audit_log_tax_id = fields.Many2one(
        comodel_name='account.tax',
        string="Tax",
        compute="_compute_audit_log_related_record_id",
        search="_search_account_audit_log_tax_id",
    )
    account_audit_log_company_id = fields.Many2one(
        comodel_name='res.company',
        string="Company ",
        compute="_compute_audit_log_related_record_id",
        search="_search_account_audit_log_company_id",
    )
    account_audit_log_activated = fields.Boolean(
        string="Audit Log Activated",
        compute="_compute_account_audit_log_activated",
        search="_search_account_audit_log_activated",
    )

    @api.depends('account_audit_log_activated', 'tracking_value_ids')
    def _compute_account_audit_log_preview(self):
        audit_messages = self.filtered('account_audit_log_activated')
        (self - audit_messages).account_audit_log_preview = False
        for message in audit_messages:
            title = message.subject or message.preview
            tracking_value_ids = message.sudo().tracking_value_ids._filter_has_field_access(self.env)
            if not title and tracking_value_ids:
                title = self.env._("Updated")
            if not title and message.subtype_id and not message.subtype_id.internal:
                title = message.subtype_id.display_name
            audit_log_preview = (title or '') + '\n'
            audit_log_preview += "\n".join(
                "%(old_value)s ⇨ %(new_value)s (%(field)s)" % {
                    'old_value': fmt_vals['oldValue']['value'],
                    'new_value': fmt_vals['newValue']['value'],
                    'field': fmt_vals['changedField'],
                }
                for fmt_vals in tracking_value_ids._tracking_value_format()
            )
            message.account_audit_log_preview = audit_log_preview

    def _search_account_audit_log_move_id(self, operator, value):
        return self._search_audit_log_related_record_id('account.move', operator, value)

    def _search_account_audit_log_account_id(self, operator, value):
        return self._search_audit_log_related_record_id('account.account', operator, value)

    def _search_account_audit_log_tax_id(self, operator, value):
        return self._search_audit_log_related_record_id('account.tax', operator, value)

    def _search_account_audit_log_company_id(self, operator, value):
        return self._search_audit_log_related_record_id('res.company', operator, value)

    def _search_account_audit_log_partner_id(self, operator, value):
        return self._search_audit_log_related_record_id('res.partner', operator, value)

    @api.depends(*[f'{field}.check_account_audit_trail' for field in MODEL_FIELD.values()])
    def _compute_account_audit_log_activated(self):
        for message in self:
            message.account_audit_log_activated = message.message_type == 'notification' and any(
                message[field].check_account_audit_trail for field in MODEL_FIELD.values()
            )

    def _search_account_audit_log_activated(self, operator, value):
        if operator not in ['=', '!='] or not isinstance(value, bool):
            raise UserError(self.env._('Operation not supported'))
        return [('message_type', '=', 'notification')] + OR([
            [(f'{field}.check_account_audit_trail', '=', True)]
            for field in MODEL_FIELD.values()
        ])

    def _compute_audit_log_related_record_id(self):
        for message in self:
            for model, field in MODEL_FIELD.items():
                record_id = message.res_id if message.res_id and message.model == model else False
                message[field] = record_id

    def _search_audit_log_related_record_id(self, model, operator, value):
        if operator in ['=', 'like', 'ilike', '!=', 'not ilike', 'not like'] and isinstance(value, str):
            res_id_domain = [('res_id', 'in', self.env[model]._search([('display_name', operator, value)]))]
        elif operator in ['=', 'in', '!=', 'not in']:
            res_id_domain = [('res_id', operator, value)]
        else:
            raise UserError(self.env._('Operation not supported'))
        return [('model', '=', model)] + res_id_domain

    @api.ondelete(at_uninstall=True)
    def _except_audit_log(self):
        if self.env.context.get('bypass_audit') is bypass_token:
            return
        for message in self:
            if message.account_audit_log_activated:
                raise UserError(self.env._("You cannot remove parts of the audit trail. Archive the record instead."))

    def write(self, vals):
        if (
            vals.keys() & {'res_id', 'res_model', 'message_type', 'subtype_id'}
            or ('subject' in vals and any(self.mapped('subject')))
            or ('body' in vals and any(self.mapped('body')))
        ):
            self._except_audit_log()
        return super().write(vals)
