from odoo import api, models, tools

# TODO:
# NOTE:
# This does not work at all; There is no company in the context
# NOTE:


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _blacklist_lock_entries_wizard_menuitem(self, debug=False):
        # OVERRIDE function in account
        if self.env.company.account_fiscal_country_id.code == 'DE':
            user_is_accountant = self.env.user.has_group('account.group_account_manager')
            return not user_is_accountant
        else:
            return super()._blacklist_lock_entries_wizard_menuitem()

    @api.model
    @tools.ormcache_context('self._uid', 'debug', keys=('lang', 'company'))
    def load_menus(self, debug):
        return super().load_menus(debug)
