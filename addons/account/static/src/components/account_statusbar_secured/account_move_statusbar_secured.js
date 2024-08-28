import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { statusBarField, StatusBarField } from "@web/views/fields/statusbar/statusbar_field";

export class AccountMoveStatusBarSecuredField extends StatusBarField {
    static template = "account.MoveStatusBarSecuredField";

    isSecured() {
        return this.props.record.data['secured'];
    }

    getCurrentItem() {
        return this.getAllItems().find((item) => item.isSelected) || _t("More");
    }
}

export const accountMoveStatusBarSecuredField = {
    ...statusBarField,
    component: AccountMoveStatusBarSecuredField,
    displayName: _t("Status with secured indicator for Journal Entries"),
    supportedTypes: ["state"],
};

registry.category("fields").add("account_move_statusbar_secured", accountMoveStatusBarSecuredField);
