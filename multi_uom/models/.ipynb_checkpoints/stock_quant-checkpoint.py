# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from psycopg2 import Error, OperationalError

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression
from odoo.tools.float_utils import float_compare, float_is_zero, float_round

_logger = logging.getLogger(__name__)


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure', compute='get_uom_is', related=False)
    uom_id_2 = fields.Many2one('uom.uom', string='UOM 2')

    @api.model
    def create(self, vals):
        """ Override to handle the "inventory mode" and create a quant as
        superuser the conditions are met.
        """
        if 'lot_id' in vals and 'uom_id_2' in vals:
            if vals['lot_id'] and vals['uom_id_2']:
                lot_uom_id = self.env['stock.lot'].search([('id', '=', vals['lot_id'])]).product_uom_id.id
                if lot_uom_id != vals['uom_id_2']:
                    raise UserError(_('Your Lot number UOM and current UOM is Not same'))
        return super(StockQuant, self).create(vals)

    @api.model
    def _get_inventory_fields_create(self):
        """ Returns a list of fields user can edit when he want to create a quant in `inventory_mode`.
        """
        res = super()._get_inventory_fields_create()
        res += ['uom_id_2']
        return res

    @api.depends('company_id', 'location_id', 'owner_id', 'product_id', 'quantity')
    def _compute_value(self):
        """ For standard and AVCO valuation, compute the current accounting
        valuation of the quants by multiplying the quantity by
        the standard price. Instead for FIFO, use the quantity times the
        average cost (valuation layers are not manage by location so the
        average cost is the same for all location and the valuation field is
        a estimation more than a real value).
        """
        for quant in self:
            quant.currency_id = quant.company_id.currency_id
            # If the user didn't enter a location yet while enconding a quant.
            if not quant.location_id:
                quant.value = 0
                return

            if not quant.location_id._should_be_valued() or\
                    (quant.owner_id and quant.owner_id != quant.company_id.partner_id):
                quant.value = 0
                continue
            if quant.product_id.cost_method == 'fifo':
                quantity = quant.product_id.quantity_svl
                if float_is_zero(quantity, precision_rounding=quant.product_id.uom_id.rounding):
                    quant.value = 0.0
                    continue
                average_cost = quant.product_id.with_company(quant.company_id).value_svl / quantity
                if quant.product_uom_id.uom_type == 'bigger':
                    quant.value = quant.product_uom_id.factor_inv * quant.quantity * quant.quantity * average_cost
                elif quant.product_uom_id.uom_type == 'smaller':
                    quant.value = quant.product_uom_id.factor_inv * quant.quantity * average_cost
                else:
                    quant.value = quant.quantity * quant.quantity * average_cost
            else:
                if quant.product_uom_id.uom_type == 'bigger':
                    quant.value = quant.product_uom_id.factor_inv * quant.quantity * quant.product_id.with_company(quant.company_id).standard_price
                elif quant.product_uom_id.uom_type == 'smaller':
                    quant.value = quant.product_uom_id.factor_inv * quant.quantity * quant.product_id.with_company(quant.company_id).standard_price
                else:
                    quant.value = quant.quantity * quant.product_id.with_company(quant.company_id).standard_price

    @api.model
    def _update_reserved_quantity(self, product_id, location_id, quantity, lot_id=None, package_id=None, owner_id=None, strict=False, uom_id=None):
        """ Increase the reserved quantity, i.e. increase `reserved_quantity` for the set of quants
        sharing the combination of `product_id, location_id` if `strict` is set to False or sharing
        the *exact same characteristics* otherwise. Typically, this method is called when reserving
        a move or updating a reserved move line. When reserving a chained move, the strict flag
        should be enabled (to reserve exactly what was brought). When the move is MTS,it could take
        anything from the stock, so we disable the flag. When editing a move line, we naturally
        enable the flag, to reflect the reservation according to the edition.

        :return: a list of tuples (quant, quantity_reserved) showing on which quant the reservation
            was done and how much the system was able to reserve on it
        """
        self = self.sudo()
        rounding = product_id.uom_id.rounding
        quants = self._gather(product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict)
        reserved_quants = []

        if float_compare(quantity, 0, precision_rounding=rounding) > 0:
            # if we want to reserve
            available_quantity = self._get_available_quantity(product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict)
            if float_compare(quantity, available_quantity, precision_rounding=rounding) > 0:
                raise UserError(_('It is not possible to reserve more products of %s than you have in stock.', product_id.display_name))
        elif float_compare(quantity, 0, precision_rounding=rounding) < 0:
            # if we want to unreserve
            available_quantity = sum(quants.mapped('reserved_quantity'))
            if float_compare(abs(quantity), available_quantity, precision_rounding=rounding) > 0:
                raise UserError(_('It is not possible to unreserve more products of %s than you have in stock.', product_id.display_name))
        else:
            return reserved_quants

        if uom_id:
            for quant in quants:
                if uom_id.id == quant.product_uom_id.id:
                    if float_compare(quantity, 0, precision_rounding=rounding) > 0:
                        max_quantity_on_quant = quant.quantity - quant.reserved_quantity
                        if float_compare(max_quantity_on_quant, 0, precision_rounding=rounding) <= 0:
                            continue
                        max_quantity_on_quant = min(max_quantity_on_quant, quantity)
                        quant.reserved_quantity += max_quantity_on_quant
                        reserved_quants.append((quant, max_quantity_on_quant))
                        quantity -= max_quantity_on_quant
                        available_quantity -= max_quantity_on_quant
                    else:
                        max_quantity_on_quant = min(quant.reserved_quantity, abs(quantity))
                        quant.reserved_quantity -= max_quantity_on_quant
                        reserved_quants.append((quant, -max_quantity_on_quant))
                        quantity += max_quantity_on_quant
                        available_quantity += max_quantity_on_quant

                    if float_is_zero(quantity, precision_rounding=rounding) or float_is_zero(available_quantity, precision_rounding=rounding):
                        break
        else:
            for quant in quants:
                if float_compare(quantity, 0, precision_rounding=rounding) > 0:
                    max_quantity_on_quant = quant.quantity - quant.reserved_quantity
                    if float_compare(max_quantity_on_quant, 0, precision_rounding=rounding) <= 0:
                        continue
                    max_quantity_on_quant = min(max_quantity_on_quant, quantity)
                    quant.reserved_quantity += max_quantity_on_quant
                    reserved_quants.append((quant, max_quantity_on_quant))
                    quantity -= max_quantity_on_quant
                    available_quantity -= max_quantity_on_quant
                else:
                    max_quantity_on_quant = min(quant.reserved_quantity, abs(quantity))
                    quant.reserved_quantity -= max_quantity_on_quant
                    reserved_quants.append((quant, -max_quantity_on_quant))
                    quantity += max_quantity_on_quant
                    available_quantity += max_quantity_on_quant

                if float_is_zero(quantity, precision_rounding=rounding) or float_is_zero(available_quantity,
                                                                                         precision_rounding=rounding):
                    break
        return reserved_quants

    @api.depends('product_id')
    @api.onchange('product_id')
    def get_uom_is(self):
        for val in self:
            if val.uom_id_2:
                val.product_uom_id = val.uom_id_2.id
            else:
                val.product_uom_id = val.product_id.uom_id.id


    @api.model
    def _update_available_quantity(self, product_id, location_id, quantity, lot_id=None, package_id=None, owner_id=None,
                                   in_date=None):
        """ Increase or decrease `reserved_quantity` of a set of quants for a given set of
        product_id/location_id/lot_id/package_id/owner_id.

        :param product_id:
        :param location_id:
        :param quantity:
        :param lot_id:
        :param package_id:
        :param owner_id:
        :param datetime in_date: Should only be passed when calls to this method are done in
                                 order to move a quant. When creating a tracked quant, the
                                 current datetime will be used.
        :return: tuple (available_quantity, in_date as a datetime)
        """
        # if lot_id and lot_id.uom_id_2:
        #     if product_id.uom_id.id != lot_id.uom_id_2.id:
        #         quantity = product_id.uom_id._compute_quantity(quantity, lot_id.uom_id_2, rounding_method='HALF-UP')
        self = self.sudo()
        quants = self._gather(product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id,
                              strict=True)

        incoming_dates = [d for d in quants.mapped('in_date') if d]
        incoming_dates = [fields.Datetime.from_string(incoming_date) for incoming_date in incoming_dates]
        if in_date:
            incoming_dates += [in_date]
        # If multiple incoming dates are available for a given lot_id/package_id/owner_id, we
        # consider only the oldest one as being relevant.
        if incoming_dates:
            in_date = fields.Datetime.to_string(min(incoming_dates))
        else:
            in_date = fields.Datetime.now()

        for quant in quants:
            try:
                with self._cr.savepoint(flush=False):  # Avoid flush compute store of package
                    self._cr.execute("SELECT 1 FROM stock_quant WHERE id = %s FOR UPDATE NOWAIT", [quant.id],
                                     log_exceptions=False)
                    quant.write({
                        'quantity': quant.quantity + quantity,
                        'in_date': in_date,
                    })
                    break
            except OperationalError as e:
                if e.pgcode == '55P03':  # could not obtain the lock
                    continue
                else:
                    # Because savepoint doesn't flush, we need to invalidate the cache
                    # when there is a error raise from the write (other than lock-error)
                    self.clear_caches()
                    raise
        else:
            self.create({
                'product_id': product_id.id,
                'location_id': location_id.id,
                'quantity': quantity,
                'lot_id': lot_id and lot_id.id,
                'uom_id_2': lot_id.uom_id_2.id if lot_id.uom_id_2 else False,
                'package_id': package_id and package_id.id,
                'owner_id': owner_id and owner_id.id,
                'in_date': in_date,
            })
        return self._get_available_quantity(product_id, location_id, lot_id=lot_id, package_id=package_id,
                                            owner_id=owner_id, strict=False,
                                            allow_negative=True), fields.Datetime.from_string(in_date)

    def _gather(self, product_id, location_id, lot_id=None, package_id=None, owner_id=None, strict=False):
        self.env['stock.quant'].flush(['location_id', 'owner_id', 'package_id', 'lot_id', 'product_id'])
        self.env['product.product'].flush(['virtual_available'])
        removal_strategy = self._get_removal_strategy(product_id, location_id)
        removal_strategy_order = self._get_removal_strategy_order(removal_strategy)
        domain = [
            ('product_id', '=', product_id.id),
        ]
        if not strict:
            if lot_id and lot_id.uom_id_2:
                domain = expression.AND([[('product_uom_id', '=', lot_id.uom_id_2.id)], domain])
            if lot_id:
                domain = expression.AND([[('lot_id', '=', lot_id.id)], domain])
            if package_id:
                domain = expression.AND([[('package_id', '=', package_id.id)], domain])
            if owner_id:
                domain = expression.AND([[('owner_id', '=', owner_id.id)], domain])
            domain = expression.AND([[('location_id', 'child_of', location_id.id)], domain])
        else:
            domain = expression.AND([[('lot_id', '=', lot_id and lot_id.id or False)], domain])
            if lot_id and lot_id.uom_id_2:
                domain = expression.AND([[('uom_id_2', '=', lot_id.uom_id_2.id)], domain])
            domain = expression.AND([[('package_id', '=', package_id and package_id.id or False)], domain])
            domain = expression.AND([[('owner_id', '=', owner_id and owner_id.id or False)], domain])
            domain = expression.AND([[('location_id', '=', location_id.id)], domain])

        # Copy code of _search for special NULLS FIRST/LAST order
        self.check_access_rights('read')
        query = self._where_calc(domain)
        self._apply_ir_rules(query, 'read')
        from_clause, where_clause, where_clause_params = query.get_sql()
        where_str = where_clause and (" WHERE %s" % where_clause) or ''
        query_str = 'SELECT "%s".id FROM ' % self._table + from_clause + where_str + " ORDER BY " + removal_strategy_order
        self._cr.execute(query_str, where_clause_params)
        res = self._cr.fetchall()
        # No uniquify list necessary as auto_join is not applied anyways...
        return self.browse([x[0] for x in res])
