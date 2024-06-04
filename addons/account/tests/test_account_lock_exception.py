from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged, new_test_user
from odoo import fields
from odoo.exceptions import UserError

from freezegun import freeze_time
from datetime import timedelta


@freeze_time(fields.Datetime.now())
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

        cls.soft_lock_date_info = [
            ('fiscalyear_lock_date', 'out_invoice'),
            ('tax_lock_date', 'out_invoice'),
            ('sale_lock_date', 'out_invoice'),
            ('purchase_lock_date', 'in_invoice'),
        ]

    def test_local_exception_move_edit_multi_user(self):
        """
        Test that an exception for a specific user only works for that user.
        """
        for lock_date_field, move_type in self.soft_lock_date_info:
            with self.subTest(lock_date_field=lock_date_field, move_type=move_type), self.cr.savepoint() as sp:
                move = self.init_invoice(move_type, invoice_date='2016-01-01', post=True, amounts=[1000.0], taxes=self.tax_sale_a)

                # Lock the move
                self.company[lock_date_field] = fields.Date.from_string('2020-01-01')
                with self.assertRaises(UserError), self.cr.savepoint():
                    move.button_draft()

                # Add an exception to make the move editable (for the current user)
                now = fields.Datetime.now()
                self.env['account.lock_exception'].create({
                    'company_id': self.company.id,
                    'user_id': self.env.user.id,
                    lock_date_field: fields.Date.from_string('2010-01-01'),
                    'start_datetime': now,
                    'end_datetime': now + timedelta(hours=24),
                    'reason': 'test_local_exception_move_edit_multi_user',
                })
                move.button_draft()
                move.action_post()

                # Check that the exception does not apply to other users
                with self.assertRaises(UserError), self.cr.savepoint():
                    move.with_user(self.other_user).button_draft()
                sp.close()  # Rollback to ensure all subtests start in the same situation

    def test_global_exception_move_edit_multi_user(self):
        """
        Test that an exception without a specified user works for any user.
        """
        for lock_date_field, move_type in self.soft_lock_date_info:
            with self.subTest(lock_date_field=lock_date_field, move_type=move_type), self.cr.savepoint() as sp:
                move = self.init_invoice(move_type, invoice_date='2016-01-01', post=True, amounts=[1000.0], taxes=self.tax_sale_a)

                # Lock the move
                self.company[lock_date_field] = fields.Date.from_string('2020-01-01')
                with self.assertRaises(UserError), self.cr.savepoint():
                    move.button_draft()

                # Add a global exception to make the move editable for everyone
                now = fields.Datetime.now()
                self.env['account.lock_exception'].create({
                    'company_id': self.company.id,
                    'user_id': False,
                    lock_date_field: fields.Date.from_string('2010-01-01'),
                    'start_datetime': now,
                    'end_datetime': now + timedelta(hours=24),
                    'reason': 'test_global_exception_move_edit_multi_user',
                })

                move.button_draft()
                move.action_post()

                move.with_user(self.other_user).button_draft()

                sp.close()  # Rollback to ensure all subtests start in the same situation

    def test_local_exception_wrong_company(self):
        """
        Test that an exception only works for the specified company.
        """
        for lock_date_field, move_type in self.soft_lock_date_info:
            with self.subTest(lock_date_field=lock_date_field, move_type=move_type), self.cr.savepoint() as sp:
                move = self.init_invoice(move_type, invoice_date='2016-01-01', post=True, amounts=[1000.0], taxes=self.tax_sale_a)
                # Lock the move
                self.company[lock_date_field] = fields.Date.from_string('2020-01-01')
                with self.assertRaises(UserError), self.cr.savepoint():
                    move.button_draft()

                # Add an exception for another company
                now = fields.Datetime.now()
                self.env['account.lock_exception'].create({
                    'company_id': self.company_data_2['company'].id,
                    'user_id': self.env.user.id,
                    lock_date_field: fields.Date.from_string('2010-01-01'),
                    'start_datetime': now,
                    'end_datetime': now + timedelta(hours=24),
                    'reason': 'test_local_exception_move_edit_multi_user',
                })

                # Check that the exception is insufficient
                with self.assertRaises(UserError), self.cr.savepoint():
                    move.button_draft()

                sp.close()  # Rollback to ensure all subtests start in the same situation

    def test_local_exception_insufficient(self):
        """
        Test that the exception only works if the specified lock date is actually before the accounting date.
        """
        for lock_date_field, move_type in self.soft_lock_date_info:
            with self.subTest(lock_date_field=lock_date_field, move_type=move_type), self.cr.savepoint() as sp:
                move = self.init_invoice(move_type, invoice_date='2016-01-01', post=True, amounts=[1000.0], taxes=self.tax_sale_a)

                # Lock the move
                self.company[lock_date_field] = fields.Date.from_string('2020-01-01')
                with self.assertRaises(UserError), self.cr.savepoint():
                    move.button_draft()

                # Add an exception before the lock date but not before the date of the test_invoice
                now = fields.Datetime.now()
                self.env['account.lock_exception'].create({
                    'company_id': self.company.id,
                    'user_id': self.env.user.id,
                    lock_date_field: fields.Date.from_string('2016-01-01'),
                    'start_datetime': now,
                    'end_datetime': now + timedelta(hours=24),
                    'reason': 'test_local_exception_move_edit_multi_user',
                })

                # Check that the exception is insufficient
                with self.assertRaises(UserError), self.cr.savepoint():
                    move.button_draft()

                sp.close()  # Rollback to ensure all subtests start in the same situation

    def test_expired_exception(self):
        """
        Test that the exception does not work if we are past the `end_datetime` of the exception.
        """
        for lock_date_field, move_type in self.soft_lock_date_info:
            with self.subTest(lock_date_field=lock_date_field, move_type=move_type), self.cr.savepoint() as sp:
                move = self.init_invoice(move_type, invoice_date='2016-01-01', post=True, amounts=[1000.0], taxes=self.tax_sale_a)

                # Lock the move
                self.company[lock_date_field] = fields.Date.from_string('2020-01-01')
                with self.assertRaises(UserError), self.cr.savepoint():
                    move.button_draft()

                # Add an exception to make the move editable (for the current user)
                now = fields.Datetime.now()
                self.env['account.lock_exception'].create({
                    'company_id': self.company.id,
                    'user_id': self.env.user.id,
                    lock_date_field: fields.Date.from_string('2010-01-01'),
                    'start_datetime': now - timedelta(hours=24),
                    'end_datetime': now - timedelta(milliseconds=1),
                    'reason': 'test_expired_exception',
                })
                with self.assertRaises(UserError), self.cr.savepoint():
                    move.button_draft()

                sp.close()  # Rollback to ensure all subtests start in the same situation

    def test_future_exception(self):
        """
        Test that the exception does not work if we have not reached the `start_datetime` yet.
        """
        for lock_date_field, move_type in self.soft_lock_date_info:
            with self.subTest(lock_date_field=lock_date_field, move_type=move_type), self.cr.savepoint() as sp:
                move = self.init_invoice(move_type, invoice_date='2016-01-01', post=True, amounts=[1000.0], taxes=self.tax_sale_a)

                # Lock the move
                self.company[lock_date_field] = fields.Date.from_string('2020-01-01')
                with self.assertRaises(UserError), self.cr.savepoint():
                    move.button_draft()

                # Add an exception to make the move editable (for the current user)
                now = fields.Datetime.now()
                self.env['account.lock_exception'].create({
                    'company_id': self.company.id,
                    'user_id': self.env.user.id,
                    lock_date_field: fields.Date.from_string('2010-01-01'),
                    'start_datetime': now + timedelta(milliseconds=1),
                    'end_datetime': now + timedelta(hours=24),
                    'reason': 'test_future_exception',
                })
                with self.assertRaises(UserError), self.cr.savepoint():
                    move.button_draft()

                sp.close()  # Rollback to ensure all subtests start in the same situation

    def test_revoked_exception(self):
        for lock_date_field, move_type in self.soft_lock_date_info:
            with self.subTest(lock_date_field=lock_date_field, move_type=move_type), self.cr.savepoint() as sp:
                move = self.init_invoice(move_type, invoice_date='2016-01-01', post=True, amounts=[1000.0], taxes=self.tax_sale_a)

                # Lock the move
                self.company[lock_date_field] = fields.Date.from_string('2020-01-01')
                with self.assertRaises(UserError), self.cr.savepoint():
                    move.button_draft()

                # Add an exception to make the move editable (for the current user)
                now = fields.Datetime.now()
                exception = self.env['account.lock_exception'].create({
                    'company_id': self.company.id,
                    'user_id': self.env.user.id,
                    lock_date_field: fields.Date.from_string('2010-01-01'),
                    'start_datetime': now,
                    'end_datetime': now + timedelta(hours=24),
                    'reason': 'test_local_exception_move_edit_multi_user',
                })
                move.button_draft()
                move.action_post()

                exception.action_revoke()

                # Check that the exception does not work anymore
                with self.assertRaises(UserError), self.cr.savepoint():
                    move.button_draft()

                sp.close()  # Rollback to ensure all subtests start in the same situation

    def test_local_exception_wrong_field(self):
        for lock_date_field, move_type, exception_lock_date_field in [
            ('fiscalyear_lock_date', 'out_invoice', 'tax_lock_date'),
            ('tax_lock_date', 'out_invoice', 'fiscalyear_lock_date'),
            ('sale_lock_date', 'out_invoice', 'purchase_lock_date'),
            ('purchase_lock_date', 'in_invoice', 'sale_lock_date'),
        ]:
            with self.subTest(lock_date_field=lock_date_field, move_type=move_type), self.cr.savepoint() as sp:
                move = self.init_invoice(move_type, invoice_date='2016-01-01', post=True, amounts=[1000.0], taxes=self.tax_sale_a)
                # Lock the move
                self.company[lock_date_field] = fields.Date.from_string('2020-01-01')
                with self.assertRaises(UserError), self.cr.savepoint():
                    move.button_draft()

                # Add an exception for a different lock date field
                now = fields.Datetime.now()
                self.env['account.lock_exception'].create({
                    'company_id': self.company_data_2['company'].id,
                    'user_id': self.env.user.id,
                    exception_lock_date_field: fields.Date.from_string('2010-01-01'),
                    'start_datetime': now,
                    'end_datetime': now + timedelta(hours=24),
                    'reason': 'test_local_exception_wrong_field',
                })

                # Check that the exception is insufficient
                with self.assertRaises(UserError), self.cr.savepoint():
                    move.button_draft()

                sp.close()  # Rollback to ensure all subtests start in the same situation
