import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { escape } from "@web/core/utils/strings";
import { statusBarField, StatusBarField } from "@web/views/fields/statusbar/statusbar_field";
import { markup } from "@odoo/owl";

export class AccountMoveStatusBarSecuredField extends StatusBarField {

    get isSecured() {
        return this.props.record.data['secured'];
    }

    getAllItems() {
        const items = super.getAllItems();
        for (const item of items) {
            if (item.value == 'posted') {
                const lock_classes = this.isSecured ? 'fa-lock text-success' : 'fa-unlock text-warning'
                item.label = markup(`${escape(item.label)}<i class="fa fa-fw ms-1 ${lock_classes}"/>`)
            }
        }
        return items;
    }
}

export const accountMoveStatusBarSecuredField = {
    ...statusBarField,
    component: AccountMoveStatusBarSecuredField,
    displayName: _t("Status with secured indicator for Journal Entries"),
    supportedTypes: ["state"],
};

registry.category("fields").add("account_move_statusbar_secured", accountMoveStatusBarSecuredField);
