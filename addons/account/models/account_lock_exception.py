from odoo import _, api, fields, models

from odoo.tools import create_index


class AccountLockException(models.Model):
    _name = "account.lock_exception"
    _description = "Account Lock Exception"
    _inherit = ['mail.thread.main.attachment', 'mail.activity.mixin']

    state = fields.Selection([
         ('active', 'Active'),
         ('revoked', 'Revoked'),
        ],
        string="State",
        tracking=True,
        default='active',
        required=True,
        readonly=True,
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        readonly=True,
        default=lambda self: self.env.company,
    )

    # An exception w/o user_id is an exception for everyone
    user_id = fields.Many2one(
        'res.users',
        string='User',
        default=lambda self: self.env.user,
    )

    reason = fields.Char(
        string='Reason',
    )

    start_datetime = fields.Datetime(
        'Start Date',
        default=fields.Datetime.now,
        required=True,
    )

    # An exception without `end_datetime` is valid forever
    end_datetime = fields.Datetime(
        'End Date',
    )

    revocation_datetime = fields.Datetime(
        'Revocation Date',
        help="The date / time when the exception was last revoked."
    )

    # Lock date fields; c.f. res.company
    # An unset lock date field means the exception does not change this field.
    # (It is not possible to remove a lock date completely).

    fiscalyear_lock_date = fields.Date(
        string="Everyone Lock Date",
        help="The date the Everyone Lock Date is set to by this exception. If no date is set the lock date is not changed."
    )

    tax_lock_date = fields.Date(
        string="Tax Return Lock Date",
        help="The date the Tax Lock Date is set to by this exception. If no date is set the lock date is not changed."
    )

    sale_lock_date = fields.Date(
        string='Lock Sales',
        help="The date the Sale Lock Date is set to by this exception. If no date is set the lock date is not changed."
    )

    purchase_lock_date = fields.Date(
        string='Lock Purchases',
        help="The date the Purchase Lock Date is set to by this exception. If no date is set the lock date is not changed."
    )

    def init(self):
        super().init()
        create_index(self.env.cr,
                     indexname='account_lock_exception_id_company_id_idx',
                     tablename=self._table,
                     expressions=['company_id', 'start_datetime', 'end_datetime'])

    def _compute_display_name(self):
        for record in self:
            record.display_name = _("Lock Date Exception %s", record.id)

    @api.model_create_multi
    def create(self, vals_list):
        exceptions = super().create(vals_list)
        for exception in exceptions:
            company = exception.company_id
            changed_locks = [
                 (field, exception[field])
                 for field in [
                    'fiscalyear_lock_date',
                    'tax_lock_date',
                    'sale_lock_date',
                    'purchase_lock_date',
                 ]
                 if exception[field]
               ]
            tracking_value_ids = []
            for field, value in changed_locks:
                field_info = exception.fields_get([field])[field]
                tracking_values = self.env['mail.tracking.value']._create_tracking_values(
                    company[field], value, field, field_info, exception
                )
                tracking_value_ids.append([0, 0, tracking_values])
            # In case there is no explicit end datetime "forever" is implied by not mentioning an end datetime
            end_datetime_string = _(" valid until %s", exception.end_datetime) if exception.end_datetime else ""
            reason_string = _(" for '%s'", exception.reason) if exception.reason else ""
            company_chatter_message = _(
                "%(exception)s for %(user)s%(end_datetime_string)s%(reason)s.",
                exception=exception._get_html_link(title=_("Exception")),
                user=exception.user_id.display_name if exception.user_id else _("everyone"),
                end_datetime_string=end_datetime_string,
                reason=reason_string,
            )
            company.sudo().message_post(
                body=company_chatter_message,
                tracking_value_ids=tracking_value_ids,
            )
        return exceptions

    def action_reactivate(self):
        """Resets a not 'active' exception back to 'active'."""
        for record in self:
            if record.state != 'active':
                record.state = 'active'

    def action_revoke(self):
        """Revokes an active exception."""
        for record in self:
            if record.state == 'active':
                record.revocation_datetime = fields.Datetime.now()
                record.state = 'revoked'

    def _get_audit_trail_during_exception_domain(self):
        now = fields.Datetime.now()
        revocation_datetime = self.revocation_datetime if self.state == 'revoked' else None
        end_datetime = min(self.end_datetime or now, revocation_datetime or now)

        return [
            ('model', '=', 'account.move'),
            ('account_audit_log_activated', '=', True),
            ('message_type', '=', 'notification'),
            ('date', '>=', self.start_datetime),
            ('date', '<=', end_datetime),
        ]

    def action_show_audit_trail_during_exception(self):
        self.ensure_one()
        return {
            'name': _("Audit Trail during the Exception"),
            'type': 'ir.actions.act_window',
            'res_model': 'mail.message',
            'views': [(self.env.ref('account.view_message_tree_audit_log').id, 'tree'), (False, 'form')],
            'search_view_id': [self.env.ref('account.view_message_tree_audit_log_search').id],
            'domain': self._get_audit_trail_during_exception_domain(),
        }
