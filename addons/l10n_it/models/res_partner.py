# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    l10n_it_is_regular_exporter = fields.Boolean(
        string='Is Regular Exporter',
        default=False,
        help="Enable this checkbox to specify a Declaration of Intent on this partner which is then considered a Regular Exporter"
    )

    l10n_it_declaration_of_intent_ids = fields.One2many(
        'l10n_it.declaration_of_intent',
        'partner_id',
        string="Available Declarations of Intent of this partner",
        domain=lambda self: [('company_id', '=', self.env.company.id)],
    )
