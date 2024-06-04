from markupsafe import Markup

from odoo import _, api, Command, fields, models

from odoo.tools import create_index


class AccountLockException(models.Model):
    _name = "account.lock_exception"
    _description = "Account Lock Exception"

    # TODO: specify _order

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        readonly=True,
        default=lambda self: self.env.company
    )

    # TODO: ?: allow exceptions for multiple users
    # An exception w/o user_id is an exception for everyone
    user_id = fields.Many2one(
        'res.users',
        string='User',
        default=lambda self: self.env.user
    )

    reason = fields.Char(
        string='Reason',
        required=True,
    )

    start_datetime = fields.Datetime(
        'Start Date',
        default=fields.Datetime.now,
        required=True,
    )

    # no end_datetime means that the exception is valid forever
    end_datetime = fields.Datetime(
        'End Date',
    )

    # lock date fields; c.f. res.company
    # TODO: ?: add help strings

    fiscalyear_lock_date = fields.Date(
        string="All Users Lock Date",
    )

    tax_lock_date = fields.Date(
        string="Tax Return Lock Date",
    )

    sale_lock_date = fields.Date(
        string='Lock Sales',
    )

    purchase_lock_date = fields.Date(
        string='Lock Purchases',
    )

    last_modified_move_ids = fields.Many2many(
        string='Modified Journal Entries',
        comodel_name='account.move',
        compute='_compute_last_modified_move_ids',
        help="Journal Entries last modified while the exception was valid",
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

    def _compute_last_modified_move_ids(self):
        for exception in self:
            last_modified_moves = self.env['account.move'].search(exception._get_moves_last_modified_during_domain())
            exception.last_modified_move_ids = [Command.set(last_modified_moves.ids)]

    def _get_moves_last_modified_during_domain(self):
        self.ensure_one()
        domain = [
            ('write_date', '>=', self.start_datetime),
        ]
        if self.end_datetime:
            domain.append(('write_date', '<=', self.end_datetime))
        if self.user_id:
            domain.append(('write_uid', '=', self.user_id.id))
        return domain

    # TODO: ?: as computed field directly on view
    def action_show_moves_last_modified_during(self):
        self.ensure_one()
        return {
            'name': _("Journal entries last modified during the exception"),
            'type': 'ir.actions.act_window',
            'view_mode': 'tree',
            'res_model': 'account.move',
            'domain': self._get_moves_last_modified_during_domain(),
        }

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
            changed_locks_html = ""
            for field, value in changed_locks:
                # TODO: format
                # TODO: check whether `.string` is translated
                changed_locks_html += f"<li>{company[field]} → {value} <i>({company._fields[field].string})</i></li>"
            company_chatter_message = Markup(_(
                "%(exception)s for %(user)s until %(end_datetime)s for '%(reason)s'.\n%(changed_locks)s",
                exception=exception._get_html_link(title=_("New exception")),
                user=exception.user_id._get_html_link() if exception.user_id else _("everyone"),
                end_datetime=exception.end_datetime,
                reason=exception.reason,
                changed_locks=Markup(changed_locks_html),
            ))
            exception.company_id.message_post(body=company_chatter_message)
        return exceptions
