# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Italy - Sale',
    'countries': ['it'],
    'version': '0.1',
    'depends': [
        'l10n_it',
        'sale',
    ],
    'auto_install': True,
    'description': """Italy Sale""",
    'category': 'Localization',
    'data': [
        'views/l10n_it_declaration_of_intent_views.xml',
        'views/sale_ir_actions_report_templates.xml',
        'views/sale_order_views.xml',
    ],
    'license': 'LGPL-3',
}
