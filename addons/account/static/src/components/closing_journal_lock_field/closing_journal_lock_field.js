/** @odoo-module */

import { Component, onWillStart, useSubEnv } from "@odoo/owl";

import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { X2ManyField } from "@web/views/fields/x2many/x2many_field";


class ClosingJournalLockCheckBox extends Component {
    static template = "account.ClosingJournalLockCheckBox";
    static props = { companyId: Number, journalId: Number, disabled: Boolean}

    //TODO OCO quand on fait un discard changes, il garde la case cochée => comment on gère ça ? => un useState, c'est pas ouf, si ? On recalculerait tout je pense :/ (n²)
    setup() {
        onWillStart(async () => {
            this.locked = Boolean(this.getLockRecord());
        });
    }

    getLockRecord() {
        for (const record of this.env.lock_x2many_widget.lockRecords) {
            if (record.data.company_id[0] === this.props.companyId && record.data.journal_id[0] === this.props.journalId) {
                return record;
            }
        }
        return null;
    }

    async toggleLock() {
        if (this.locked) {
            let record = this.getLockRecord();
            this.env.lock_x2many_widget.deleteLockRecord(record);
        }
        else
            await this.env.lock_x2many_widget.addLockRecord(this.props.companyId, this.props.journalId);

        this.locked = !this.locked;
    }

}

export class ClosingJournalLockField extends X2ManyField {

    //TODO OCO là, c'est community, mais ça devrait peut-être être en enterprise ?

    static template = "account.ClosingJournalLockField";
    static props = { ...standardFieldProps };
    static components = { ClosingJournalLockCheckBox };

    setup() {
        super.setup();
        this.orm = useService("orm");

        onWillStart(async () => {
            await this.initialize_widget_data();
        });

        useSubEnv({
            lock_x2many_widget: this,
        });
    }

    async initialize_widget_data() {
        this.axes_data = await this.orm.call(
            "account.report.closing",
            "get_journals_lock_grid_axes_data",
            [
                null,
                this.props.record.data.company_ids.currentIds,
            ],
        );

        this.company_name_map = {}
        for (const company_data of this.axes_data['companies']) {
            this.company_name_map[company_data['id']] = company_data['name'];
        }

        this.axes_data['journals'].sort((a, b) => {
            let comparator = this.company_name_map[a['company_id']].localeCompare(this.company_name_map[b['company_id']]);
            if (comparator !== 0)
                return comparator;
            return a['name'].localeCompare(b['name']);
        });

        this.axes_data['companies'].sort((a, b) => a['name'].localeCompare(b['name']));
    }

    get lockRecords() {
        return this.list.records;
    }

    deleteLockRecord(record) {
        this.list.delete(record);
    }

    async addLockRecord(companyId, journalId) {
        await this.onAdd({context: {default_company_id: companyId, default_journal_id: journalId}, editable: true});
  }
}

export const closingJournalLockField = {
    component: ClosingJournalLockField,
    supportedTypes: ["many2many"],
    relatedFields: [{ name: "company_id", type: "many2one", readonly: false}, { name: "journal_id", type: "many2one", readonly: false }],
};


registry.category("fields").add("closing_journal_lock", closingJournalLockField);
