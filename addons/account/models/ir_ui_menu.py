from odoo import models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _blacklist_lock_entries_wizard_menuitem(self, debug=False):
        user_is_accountant = self.env.user.has_group('account.group_account_manager')
        user_is_in_debug = self.env.user.has_group('base.group_no_one')
        return not user_is_accountant or not user_is_in_debug

    def _load_menus_blacklist(self):
        res = super()._load_menus_blacklist()
        if not any(company.check_account_audit_trail for company in self.env.user.company_ids):
            res.append(self.env.ref('account.account_audit_trail_menu').id)
        if self._blacklist_lock_entries_wizard_menuitem():
            res.append(self.env.ref('account.menu_action_lock_entries').id)
        return res
