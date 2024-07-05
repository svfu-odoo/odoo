# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import models


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    def _load(self, company):
        res = super()._load(company)
        template = company.chart_template_id
        if template == self.env.ref('l10n_it.l10n_it_chart_template_generic'):
            doi_tax = self.env.ref(f'l10n_it_edi_doi.{company.id}_00di')
            doi_tax.write({
                'l10n_it_has_exoneration': True,
                'l10n_it_kind_exoneration': 'N3.5',
                'l10n_it_law_reference': 'art. 8, c. 1, lett. c) D.P.R. 633/1972',
            })
            company.l10n_it_edi_doi_tax_id = doi_tax

            company.l10n_it_edi_doi_fiscal_position_id = self.env.ref(f'l10n_it_edi_doi.{company.id}_declaration_of_intent_fiscal_position')
        return res
