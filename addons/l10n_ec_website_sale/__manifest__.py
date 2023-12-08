# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Ecuadorian Website',
    'countries': ['ec'],
    'version': '1.0',
    'category': 'Accounting/Localizations/Website',
    'description': """Make ecommerce work for Ecuador.""",
    'depends': [
        'website_sale',
        'l10n_ec',
    ],
    'data': [
        'data/ir_model_fields.xml',
        'views/website_sales_templates.xml',
        'views/payment_method_views.xml',
    ],
    'demo': [
        'demo/website_demo.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'auto_install': True,
    'license': 'LGPL-3',
}
