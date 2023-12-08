# Part of Odoo. See LICENSE file for full copyright and licensing details.

from . import controllers
from . import models

def post_init_hook(env):
    payment_demo = env['ir.module.module'].sudo().search([
        ('name', '=', 'payment_demo'),
        ('state', 'not in', ['installed', 'to install', 'to upgrade']),
    ])
    if payment_demo:
        payment_demo.button_install()
