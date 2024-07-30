# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class Users(models.Model):
    _inherit = 'res.users'

    # The lock date fields are explicitly invalidated when
    #   * writing the corresponding lock date field on any company
    #   * an exception for that field is created (for any company)
    #   * an exception for that field is revoked (for any company)
    fiscalyear_lock_date = fields.Date(compute='_compute_fiscalyear_lock_date')
    tax_lock_date = fields.Date(compute='_compute_tax_lock_date')
    sale_lock_date = fields.Date(compute='_compute_sale_lock_date')
    purchase_lock_date = fields.Date(compute='_compute_purchase_lock_date')

    @api.depends('company_id')
    @api.depends_context('company')
    def _compute_fiscalyear_lock_date(self):
        company = self.env.company
        for user in self:
            user.fiscalyear_lock_date = company.with_user(user)._get_user_lock_date('fiscalyear_lock_date')

    @api.depends('company_id')
    @api.depends_context('company')
    def _compute_tax_lock_date(self):
        company = self.env.company
        for user in self:
            user.tax_lock_date = company.with_user(user)._get_user_lock_date('tax_lock_date')

    @api.depends('company_id')
    @api.depends_context('company')
    def _compute_sale_lock_date(self):
        company = self.env.company
        for user in self:
            user.sale_lock_date = company.with_user(user)._get_user_lock_date('sale_lock_date')

    @api.depends('company_id')
    @api.depends_context('company')
    def _compute_purchase_lock_date(self):
        company = self.env.company
        for user in self:
            user.purchase_lock_date = company.with_user(user)._get_user_lock_date('purchase_lock_date')


class GroupsView(models.Model):
    _inherit = 'res.groups'

    @api.model
    def get_application_groups(self, domain):
        # Overridden in order to remove 'Show Full Accounting Features' and
        # 'Show Full Accounting Features - Readonly' in the 'res.users' form view to prevent confusion
        group_account_user = self.env.ref('account.group_account_user', raise_if_not_found=False)
        if group_account_user and group_account_user.category_id.xml_id == 'base.module_category_hidden':
            domain += [('id', '!=', group_account_user.id)]
        group_account_readonly = self.env.ref('account.group_account_readonly', raise_if_not_found=False)
        if group_account_readonly and group_account_readonly.category_id.xml_id == 'base.module_category_hidden':
            domain += [('id', '!=', group_account_readonly.id)]
        group_account_basic = self.env.ref('account.group_account_basic', raise_if_not_found=False)
        if group_account_basic and group_account_basic.category_id.xml_id == 'base.module_category_hidden':
            domain += [('id', '!=', group_account_basic.id)]
        return super().get_application_groups(domain)
