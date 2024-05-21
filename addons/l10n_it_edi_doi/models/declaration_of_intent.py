# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang


class L10nItDeclarationOfIntent(models.Model):
    _name = "l10n_it_edi_doi.declaration_of_intent"
    _inherit = ['mail.thread.main.attachment', 'mail.activity.mixin']
    _description = "Declaration of Intent"
    _order = 'protocol_number_part1, protocol_number_part1'

    state = fields.Selection([
         ('draft', 'Draft'),
         ('active', 'Active'),
         ('revoked', 'Revoked'),
         ('terminated', 'Terminated'),
        ],
        string="State",
        readonly=True,
        tracking=True,
        default='draft',
        help="The state of this Declaration of Intent. \n"
        "- 'Draft' means that the Declaration of Intent still needs to be confirmed before being usable. \n"
        "- 'Active' means that the Declaration of Intent is usable. \n"
        "- 'Terminated' designates that the Declaration of Intent has been marked as not to use anymore without invalidating usages of it. \n"
        "- 'Revoked' means the Declaration of Intent should not have been used. You will probably need to revert previous usages of it, if any.\n")

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

    invoiced = fields.Monetary(
        string='Invoiced',
        compute='_compute_invoiced',
        store=True, readonly=True,
        help="Total amount of sales of services / goods under this Declaration of Intent",
    )

    not_yet_invoiced = fields.Monetary(
        string='Not Yet Invoiced',
        compute='_compute_not_yet_invoiced',
        store=True, readonly=True,
        help="Total amount of planned sales of services / goods under this Declaration of Intent (i.e. current quotation and sales orders) that can still be invoiced",
    )

    remaining = fields.Monetary(
        string='Remaining',
        compute='_compute_remaining',
        store=True, readonly=True,
        help="Remaining amount after deduction of the Invoiced and Not Yet Invoiced amounts.",
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

    invoice_line_ids = fields.One2many(
        'account.move.line',
        'l10n_it_edi_doi_declaration_of_intent_id',
        string="Invoice Lines",
        copy=False,
        readonly=True,
    )

    sale_order_line_ids = fields.One2many(
        'sale.order.line',
        'l10n_it_edi_doi_declaration_of_intent_id',
        string="Sales Order Lines",
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

    @api.depends('invoice_line_ids', 'invoice_line_ids.move_id.state')
    def _compute_invoiced(self):
        for declaration in self:
            posted_lines = self.invoice_line_ids.filtered(lambda line: line.move_id.state == 'posted')
            declaration.invoiced = posted_lines._l10n_it_edi_doi_sum_signed_amount()

    @api.depends('sale_order_line_ids', 'sale_order_line_ids.order_id.state')
    def _compute_not_yet_invoiced(self):
        for declaration in self:
            relevant_lines = self.sale_order_line_ids.filtered(lambda line: line.order_id.state == 'sale')
            declaration.not_yet_invoiced = relevant_lines._l10n_it_edi_doi_get_amount_not_yet_invoiced()

    @api.depends('threshold', 'not_yet_invoiced', 'invoiced')
    def _compute_remaining(self):
        for record in self:
            record.remaining = record.threshold - record.invoiced - record.not_yet_invoiced

    def _build_threshold_warning_message(self, invoiced, not_yet_invoiced):
        ''' Build a warning message that will be displayed in a yellow banner on top of a document
            if the `remaining` of the Declaration of Intent is less than 0 when including the document
            or the Declaration of Intent is revoked
            :param float invoiced:          The `declaration.invoiced` amount when including the document.
            :param float not_yet_invoiced:  The `declaration.not_yet_invoiced` amount when including the document.
            :return str:                    The warning message to be shown.
        '''
        self.ensure_one()
        updated_remaining = self.threshold - invoiced - not_yet_invoiced
        if updated_remaining >= 0:
            return ''
        return _('Pay attention, the threshold of your Declaration of Intent %s of %s is exceeded by %s, this document included.\n'
                 'Invoiced: %s; Not Yet Invoiced: %s',
                 self.display_name,
                 formatLang(self.env, self.threshold, currency_obj=self.currency_id),
                 formatLang(self.env, - updated_remaining, currency_obj=self.currency_id),
                 formatLang(self.env, invoiced, currency_obj=self.currency_id),
                 formatLang(self.env, not_yet_invoiced, currency_obj=self.currency_id),
                )

    def _get_validity_errors(self, company, partner, currency):
        """
        Check whether all declarations of intent in self are valid for the specified `company`, `partner`, `date` and `currency'.
        Violating these constraints leads to errors in the feature. They should not be ignored.
        Return all errors as a list of strings.
        """
        errors = []
        for declaration in self:
            if not company or declaration.company_id != company:
                errors.append(_("The Declaration of Intent belongs to company %s, not %s.",
                                declaration.company_id.name, company.name))
            if not currency or declaration.currency_id != currency:
                errors.append(_("The Declaration of Intent uses currency %s, not %s.",
                                declaration.currency_id.name, currency.name))
            if not partner or declaration.partner_id != partner:
                errors.append(_("The Declaration of Intent belongs to partner %s, not %s.",
                                declaration.partner_id.name, partner.name))
        return errors

    def _get_validity_warnings(self, company, partner, currency, date, invoiced_amount=0, only_blocking=False):
        """
        Check whether all declarations of intent in self are valid for the specified `company`, `partner`, `date` and `currency'.
        The checks for `date` and state of the declaration (except draft) are not considered blocking in case `invoiced_amount` is not positive.
        All other checks are considered blocking (prevent posting).
        Includes all checks from `_get_validity_errors`.
        Return all errors as a list of strings.
        """
        errors = []
        for declaration in self:
            errors.extend(declaration._get_validity_errors(company, partner, currency))
            if declaration.state == 'draft':
                errors.append(_("The Declaration of Intent is in draft."))
            if invoiced_amount > 0 or not only_blocking:
                if declaration.state != 'active':
                    state_selection = dict(declaration._fields['state']._description_selection(self.env))
                    errors.append(_("The state of the Declaration of Intent is '%s' (and not '%s').",
                                    state_selection.get(declaration.state),
                                    state_selection.get('active')))
                if not date or declaration.start_date > date or declaration.end_date < date:
                    errors.append(_("The Declaration of Intent is valid from %s to %s, not on %s.",
                                    declaration.start_date, declaration.end_date, date))
        return errors

    @api.model
    def _fetch_valid_declaration_of_intent(self, company, partner, currency, date):
        """
        Fetch a declaration of intent that is valid for the specified `company`, `partner`, `date` and `currency`
        and has not reached the threshold yet.
        """
        return self.env['l10n_it_edi_doi.declaration_of_intent'].search([
            ('state', '=', 'active'),
            ('company_id', '=', company.id),
            ('currency_id', '=', currency.id),
            ('partner_id', '=', partner.id),
            ('start_date', '<=', date),
            ('end_date', '>=', date),
            ('remaining', '>', 0),
        ], limit=1)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_linked_to_document(self):
        if self.env['account.move'].search_count([('l10n_it_edi_doi_declaration_of_intent_id', 'in', self.ids)], limit=1):
            raise UserError(_('You cannot delete the Declarations of Intent "%s". At least one of them is used on an Invoice already.', ', '.join(d.display_name for d in self)))
        if self.env['sale.order'].search_count([('l10n_it_edi_doi_declaration_of_intent_id', 'in', self.ids)], limit=1):
            raise UserError(_('You cannot delete the Declarations of Intent "%s". At least one of them is used on a Sales Order already.', ', '.join(d.display_name for d in self)))

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

    def action_reactivate(self):
        """ Resets a not 'active' Declaration of Intent back to 'active'.
        """
        for record in self:
            if record.state != 'active':
                record.state = 'active'

    def action_revoke(self):
        """ Called by the 'revoke' button of the form view.
        """
        for record in self:
            record.state = 'revoked'

    def action_terminate(self):
        """ Called by the 'terminated' button of the form view.
        """
        for record in self:
            if record.state != 'revoked':
                record.state = 'terminated'
