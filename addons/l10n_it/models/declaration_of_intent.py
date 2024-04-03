# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import formatLang


class L10nItDeclarationOfIntent(models.Model):
    _name = "l10n_it.declaration_of_intent"
    _inherit = ['mail.thread.main.attachment', 'mail.activity.mixin']
    _description = "Declaration of Intent"
    _order = 'protocol_number_part1, protocol_number_part1'

    state = fields.Selection([
         ('draft', 'Draft'),
         ('active', 'Active'),
         ('revoked', 'Revoked'),
         ('closed', 'Closed'),
        ],
        string="State",
        readonly=True,
        tracking=True,
        default='draft',
        help="The state of this Declaration of Intent. \n"
        "- 'draft' means that the Declaration of Intent still needs to be confirmed before being usable. \n"
        "- 'active' means that the Declaration of Intent is usable. \n"
        "- 'closed' designates that the Declaration of Intent has been marked as not to use anymore without invalidating usages of it."
        "- 'revoked' means the Declaration of Intent should not have been used. You will probably need to revert previous usages of it, if any.\n")

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        index=True,
        required=True,
        default=lambda self: self.env.company._accessible_branches()[:1],
    )

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Partner',
        index=True,
        required=True,
        domain=lambda self: ['|', ('is_company', '=', True), ('parent_id', '=', False)],
    )

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        default=lambda self: self.env.ref('base.EUR').id,
        required=True,
    )

    issue_date = fields.Date(
        string='Date of Issue',
        required=True,
        copy=False,
        default=fields.Date.context_today,
        help="Date on which the Declaration of Intent was issued",
    )

    start_date = fields.Date(
        string='Start Date',
        required=True,
        copy=False,
        help="First date on which the Declaration of Intent is valid",
    )

    end_date = fields.Date(
        string='End Date',
        required=True,
        copy=False,
        help="Last date on which the Declaration of Intent is valid",
    )

    threshold = fields.Monetary(
        string='Threshold',
        required=True,
        help="Total amount of services / goods you are allowed to sell without VAT under this Declaration of Intent",
    )

    consumed_amount = fields.Monetary(
        string='Consumed Amount',
        compute='_compute_consumed_amount',
        store=True, readonly=True,
        help="Total amount of sales of services / goods under this Declaration of Intent",
    )

    committed_amount = fields.Monetary(
        string='Committed Amount',
        compute='_compute_committed_amount',
        store=True, readonly=True,
        help="Total amount of planned sales of services / goods under this Declaration of Intent (i.e. quotations and sales orders)",
    )

    remaining_amount = fields.Monetary(
        string='Remaining Amount',
        compute='_compute_remaining_amount',
        store=True, readonly=True,
        help="Remaining amount after deduction of the consumed and committed amounts.",
    )

    protocol_number_part1 = fields.Char(
        string='Protocol 1',
        required=True, readonly=False,
        copy=False,
    )

    protocol_number_part2 = fields.Char(
        string='Protocol 2',
        required=True, readonly=False,
        copy=False,
    )

    invoice_ids = fields.One2many(
        'account.move',
        'l10n_it_declaration_of_intent_id',
        string="Invoices / Refunds",
        copy=False,
        readonly=True,
    )

    _sql_constraints = [
                        ('protocol_number_unique',
                         'unique(protocol_number_part1, protocol_number_part2)',
                         "The Protocol Number of a Declaration of Intent must be unique! Please choose another one."),
                        ('threshold_positive',
                         'CHECK(threshold > 0)',
                         "The Threshold of a Declaration of Intent must be positive."),
                       ]

    @api.depends('protocol_number_part1', 'protocol_number_part2')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.protocol_number_part1}-{record.protocol_number_part2}"

    @api.depends('invoice_ids', 'invoice_ids.state', 'invoice_ids.amount_total_signed', 'invoice_ids.move_type')
    def _compute_consumed_amount(self):
        if not self.ids:
            self.consumed_amount = False
            return
        domain = [
            ('l10n_it_declaration_of_intent_id', 'in', self.ids),
            ('state', '=', 'posted'),
            ('move_type', 'in', self.env['account.move'].get_invoice_types()),
        ]
        groups = self.env['account.move']._read_group(domain, ['l10n_it_declaration_of_intent_id'], ['amount_total_signed:sum'])
        treated = self.env[self._name]
        for declaration, amount_total_signed_sum in groups:
            declaration.consumed_amount = amount_total_signed_sum
            treated |= declaration
        (self - treated).consumed_amount = False

    def _compute_committed_amount(self):
        # to override in l10n_it_sale
        self.committed_amount = False

    @api.depends('threshold', 'committed_amount', 'consumed_amount')
    def _compute_remaining_amount(self):
        for record in self:
            record.remaining_amount = record.threshold - record.consumed_amount - record.committed_amount

    def _build_threshold_warning_message(self, record, updated_remaining):
        ''' Build the warning message that will be displayed in a yellow banner on top of `record`
            if the `remaining_amount` of the Declaration of Intent is less than 0 when including `record`.
            :param record:                     The record where the warning will appear (Invoice, Sales Order...).
            :param updated_remaining (float):  The `remaining_amount` when including `record`.
            :return (str):                     The warning message to be shown.
        '''
        if updated_remaining >= 0:
            return ''
        return _('Pay attention, the threshold of your Declaration of Intent %s of %s is exceeded by %s, this document included.',
                 self.display_name,
                 formatLang(self.env, self.threshold, currency_obj=self.currency_id),
                 formatLang(self.env, - updated_remaining, currency_obj=self.currency_id),
                )

    def _check_valid(self, company, partner, date, currency):
        """
        Check whether self (a single declaration of intent) is valid for the specified `company`, `partner`, `date` and `currency'.
        Raise a ValidationError in case it is not.
        """
        self.ensure_one()
        if self.state != 'active':
            raise ValidationError(_("The Declaration of Intent is not active."))
        if not company or self.company_id != company:
            raise ValidationError(_("The Declaration of Intent belongs to company %s, not %s.", self.company_id.name, company.name))
        if not currency or self.currency_id != currency:
            raise ValidationError(_("The Declaration of Intent uses currency %s, not %s.", self.currency_id.name, currency.name))
        if not partner or self.partner_id != partner:
            raise ValidationError(_("The Declaration of Intent belongs to partner %s, not %s.", self.partner_id.name, partner.name))
        if not date or self.start_date > date or self.end_date < date:
            raise ValidationError(_("The Declaration of Intent is valid from %s to %s, not on %s.", self.start_date, self.end_date, date))

    def _is_valid(self, company, partner, date, currency):
        """
        Return whether self (a single declaration of intent) is valid for the specified `company`, `partner`, `date` and `currency'.
        """
        self.ensure_one()
        try:
            self._check_valid(company, partner, date, currency)
        except ValidationError:
            return False
        return True

    @api.model
    def _fetch_valid_declaration_of_intent(self, company, partner, date, currency):
        """
        Fetch a declaration of intent that is valid for the specified `company`, `partner`, `date` and `currency`
        and has not reached the threshold yet.
        """
        return self.env['l10n_it.declaration_of_intent'].search([
            ('state', '=', 'active'),
            ('company_id', '=', company.id),
            ('currency_id', '=', currency.id),
            ('partner_id', '=', partner.id),
            ('start_date', '<=', date),
            ('end_date', '>=', date),
            ('remaining_amount', '>', 0),
        ], limit=1)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_linked_to_invoice(self):
        if self.env['account.move'].search_count([('l10n_it_declaration_of_intent_id', 'in', self.ids)], limit=1):
            raise UserError(_('You cannot delete the Declarations of Intent "%s". At least one of them is used on an Invoice already.', ', '.join(d.display_name for d in self)))

    def action_validate(self):
        """ Move a 'draft' Declaration of Intent to 'active'.
        """
        for record in self:
            if record.state == 'draft':
                record.state = 'active'

    def action_reset_to_draft(self):
        """ Resets an 'active' Declaration of Intent back to 'draft'.
        """
        for record in self:
            if record.state == 'active':
                record.state = 'draft'

    def action_revoke(self):
        """ Called by the 'revoke' button of the form view.
        """
        for record in self:
            record.state = 'revoked'

    def action_close(self):
        """ Called by the 'close' button of the form view.
        """
        for record in self:
            if record.state != 'revoked':
                record.state = 'closed'
