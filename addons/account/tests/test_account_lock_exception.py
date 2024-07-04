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

        cls.company_data_2 = cls.setup_other_company()

        # TODO: clean up
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
            ]
        })

    @classmethod
    def default_env_context(cls):
        # OVERRIDE
        return {}

    def test_local_exception_move_edit_multi_user(self):
        self.test_move.action_post()

        # Lock the move
        self.company.fiscalyear_lock_date = fields.Date.from_string('2020-01-01')
        with self.assertRaises(UserError), self.cr.savepoint():
            self.test_move.button_draft()

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
        self.test_move.button_draft()

        # Check that the exception does not apply to other users
        with self.assertRaises(UserError), self.cr.savepoint():
            self.test_move.button_draft()

    def test_global_exception_move_edit_multi_user(self):
        self.test_move.action_post()

        # Lock the move
        self.company.fiscalyear_lock_date = fields.Date.from_string('2020-01-01')
        with self.assertRaises(UserError), self.cr.savepoint():
            self.test_move.button_draft()

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

        self.test_move.button_draft()
        self.test_move.action_post()

        self.test_move.with_user(self.other_user).button_draft()

    def test_local_exception_wrong_company(self):
        self.test_move.action_post()

        # Lock the move
        self.company.fiscalyear_lock_date = fields.Date.from_string('2020-01-01')
        with self.assertRaises(UserError), self.cr.savepoint():
            self.test_move.button_draft()

        # Add an exception for another company
        now = fields.Datetime.now()
        self.env['account.lock_exception'].create({
            'company_id': self.company_data_2['company'].id,
            'user_id': self.env.user.id,
            'fiscalyear_lock_date': fields.Date.from_string('2010-01-01'),
            'start_datetime': now,
            'end_datetime': now + timedelta(hours=24),
            'reason': 'test_local_exception_move_edit_multi_user',
        })

        # Check that the exception is insufficient
        with self.assertRaises(UserError), self.cr.savepoint():
            self.test_move.button_draft()

    def test_local_exception_insufficient(self):
        self.test_move.action_post()

        # Lock the move
        self.company.fiscalyear_lock_date = fields.Date.from_string('2020-01-01')
        with self.assertRaises(UserError), self.cr.savepoint():
            self.test_move.button_draft()

        # Add an exception before the lock date but after the date of the test_move
        now = fields.Datetime.now()
        self.env['account.lock_exception'].create({
            'company_id': self.company.id,
            'user_id': self.env.user.id,
            'fiscalyear_lock_date': fields.Date.from_string('2018-01-01'),
            'start_datetime': now,
            'end_datetime': now + timedelta(hours=24),
            'reason': 'test_local_exception_move_edit_multi_user',
        })

        # Check that the exception is insufficient
        with self.assertRaises(UserError), self.cr.savepoint():
            self.test_move.button_draft()

    def test_expired_exception(self):
        self.test_move.action_post()

        # Lock the move
        self.company.fiscalyear_lock_date = fields.Date.from_string('2020-01-01')
        with self.assertRaises(UserError), self.cr.savepoint():
            self.test_move.button_draft()

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
            self.test_move.button_draft()

    def test_future_exception(self):
        self.test_move.action_post()

        # Lock the move
        self.company.fiscalyear_lock_date = fields.Date.from_string('2020-01-01')
        with self.assertRaises(UserError), self.cr.savepoint():
            self.test_move.button_draft()

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
            self.test_move.button_draft()
