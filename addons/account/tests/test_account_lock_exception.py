from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged, new_test_user
from odoo import fields
from odoo.exceptions import UserError

from datetime import timedelta


@tagged('post_install', '-at_install')
class TestAccountLockException(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.other_user = new_test_user(
            cls.env,
            name='Other User',
            login='other_user',
            password='password',
            email='other_user@example.com',
            groups_id=cls.get_default_groups().ids,
            company_id=cls.env.company.id,
        )

        # TODO: clean up this function

        cls.company_data_2 = cls.setup_other_company()
        cls.other_currency = cls.setup_other_currency('HRK')

        tax_repartition_line = cls.company_data['default_tax_sale'].refund_repartition_line_ids\
            .filtered(lambda line: line.repartition_type == 'tax')
        cls.test_move = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': fields.Date.from_string('2016-01-01'),
            'line_ids': [
                (0, None, {
                    'name': 'revenue line 1',
                    'account_id': cls.company_data['default_account_revenue'].id,
                    'debit': 500.0,
                    'credit': 0.0,
                }),
                (0, None, {
                    'name': 'revenue line 2',
                    'account_id': cls.company_data['default_account_revenue'].id,
                    'debit': 1000.0,
                    'credit': 0.0,
                    'tax_ids': [(6, 0, cls.company_data['default_tax_sale'].ids)],
                }),
                (0, None, {
                    'name': 'tax line',
                    'account_id': cls.company_data['default_account_tax_sale'].id,
                    'debit': 150.0,
                    'credit': 0.0,
                    'tax_repartition_line_id': tax_repartition_line.id,
                }),
                (0, None, {
                    'name': 'counterpart line',
                    'account_id': cls.company_data['default_account_expense'].id,
                    'debit': 0.0,
                    'credit': 1650.0,
                }),
            ]
        })
        cls.entry_line_vals_1 = {
            'name': 'Line 1',
            'account_id': cls.company_data['default_account_revenue'].id,
            'debit': 500.0,
            'credit': 0.0,
        }
        cls.entry_line_vals_2 = {
            'name': 'Line 2',
            'account_id': cls.company_data['default_account_expense'].id,
            'debit': 0.0,
            'credit': 500.0,
        }

    @classmethod
    def default_env_context(cls):
        # OVERRIDE
        return {}

    def test_local_exception_move_edit_multi_user(self):
        self.test_move.action_post()

        # Lock the move
        self.company.fiscalyear_lock_date = fields.Date.from_string('2020-01-01')
        with self.assertRaises(UserError), self.cr.savepoint():
            self.test_move.line_ids[0].write({'account_id': self.test_move.line_ids[0].account_id.copy().id})

        # Add an exception to make the move editable (for the current user)
        now = fields.Datetime.now()
        self.env['account.lock_exception'].create({
            'company_id': self.company.id,
            'user_id': self.env.user.id,
            'fiscalyear_lock_date': fields.Date.from_string('2010-01-01'),
            'start_datetime': now,
            'end_datetime': now + timedelta(hours=24),
            'reason': 'test_local_exception_move_edit_multi_user',
        })
        self.test_move.line_ids[0].write({'account_id': self.test_move.line_ids[0].account_id.copy().id})

        # Check that the exception does not apply to other users
        with self.assertRaises(UserError), self.cr.savepoint():
            self.test_move.with_user(self.other_user).line_ids[0].write({'account_id': self.test_move.line_ids[0].account_id.copy().id})

    def test_global_exception_move_edit_multi_user(self):
        self.test_move.action_post()

        # Lock the move
        self.company.fiscalyear_lock_date = fields.Date.from_string('2020-01-01')
        with self.assertRaises(UserError), self.cr.savepoint():
            self.test_move.line_ids[0].write({'account_id': self.test_move.line_ids[0].account_id.copy().id})

        # Add a global exception to make the move editable for everyone
        now = fields.Datetime.now()
        self.env['account.lock_exception'].create({
            'company_id': self.company.id,
            'user_id': False,
            'fiscalyear_lock_date': fields.Date.from_string('2010-01-01'),
            'start_datetime': now,
            'end_datetime': now + timedelta(hours=24),
            'reason': 'test_global_exception_move_edit_multi_user',
        })
        self.test_move.line_ids[0].write({'account_id': self.test_move.line_ids[0].account_id.copy().id})
        self.test_move.with_user(self.other_user).line_ids[0].write({'account_id': self.test_move.line_ids[0].account_id.copy().id})

    def test_expired_exception(self):
        self.test_move.action_post()

        # Lock the move
        self.company.fiscalyear_lock_date = fields.Date.from_string('2020-01-01')
        with self.assertRaises(UserError), self.cr.savepoint():
            self.test_move.line_ids[0].write({'account_id': self.test_move.line_ids[0].account_id.copy().id})

        # Add an exception to make the move editable (for the current user)
        now = fields.Datetime.now()
        self.env['account.lock_exception'].create({
            'company_id': self.company.id,
            'user_id': self.env.user.id,
            'fiscalyear_lock_date': fields.Date.from_string('2010-01-01'),
            'start_datetime': now - timedelta(hours=24),
            'end_datetime': now - timedelta(hours=12),
            'reason': 'test_expired_exception',
        })
        with self.assertRaises(UserError), self.cr.savepoint():
            self.test_move.line_ids[0].write({'account_id': self.test_move.line_ids[0].account_id.copy().id})

    def test_future_exception(self):
        self.test_move.action_post()

        # Lock the move
        self.company.fiscalyear_lock_date = fields.Date.from_string('2020-01-01')
        with self.assertRaises(UserError), self.cr.savepoint():
            self.test_move.line_ids[0].write({'account_id': self.test_move.line_ids[0].account_id.copy().id})

        # Add an exception to make the move editable (for the current user)
        now = fields.Datetime.now()
        self.env['account.lock_exception'].create({
            'company_id': self.company.id,
            'user_id': self.env.user.id,
            'fiscalyear_lock_date': fields.Date.from_string('2010-01-01'),
            'start_datetime': now + timedelta(hours=12),
            'end_datetime': now + timedelta(hours=24),
            'reason': 'test_future_exception',
        })
        with self.assertRaises(UserError), self.cr.savepoint():
            self.test_move.line_ids[0].write({'account_id': self.test_move.line_ids[0].account_id.copy().id})
