# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero, OrderedSet

import logging
from itertools import groupby
from odoo.tools.float_utils import float_compare, float_is_zero, float_repr, float_round
from operator import itemgetter

_logger = logging.getLogger(__name__)


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def create(self, vals):
        res = super(StockMoveLine, self).create(vals)
        for rec in res:
            quant_id = self.env['stock.quant'].search(
                [('product_id.id', '=', rec.product_id.id), ('location_id.id', '=', rec.location_id.id),
                 ('uom_id_2.id', '=', rec.product_uom_id.id)])
            if len(quant_id) > 1:
                quant_id = self.env['stock.quant'].search(
                    [('product_id.id', '=', rec.product_id.id), ('location_id.id', '=', rec.location_id.id),
                     ('uom_id_2.id', '=', rec.product_uom_id.id), ('lot_id', '=', rec.lot_id.id)])
            if quant_id:
                rec.quant_id = quant_id.id
        return res

    def _prepare_new_lot_vals(self):
        self.ensure_one()
        ml = self
        return {
            'company_id': ml.move_id.company_id.id,
            'name': ml.lot_name,
            'product_id': ml.product_id.id,
            # 'product_qty_2': ml.qty_done,
            'product_qty_2': ml.quantity_product_uom,
            'product_uom_id': ml.product_uom_id.id,
            'uom_id_2': ml.product_uom_id.id,
        }

    @api.onchange("lot_id")
    def _get_uom_on_stock_lot(self):
        for rec in self:
            rec.lot_id.uom_id_2 = self.product_uom_id

    # def _create_and_assign_production_lot(self):
    #     """ Creates and assign new production lots for move lines."""
    #     lot_vals = [{
    #         'company_id': ml.move_id.company_id.id,
    #         'name': ml.lot_name,
    #         'product_id': ml.product_id.id,
    #         # 'product_qty_2': ml.qty_done,
    #         'product_qty_2': ml.quantity_product_uom,
    #         'product_uom_id': ml.product_uom_id.id,
    #         'uom_id_2': ml.product_uom_id.id,
    #     } for ml in self]
    #     lots = self.env['stock.lot'].create(lot_vals)
    #     for ml, lot in zip(self, lots):
    #         ml._assign_production_lot(lot)

    # @api.model_create_multi
    # def create(self, vals_list):
    #     mls = super().create(vals_list)
    #
    #     def create_move(move_line):
    #         new_move = self.env['stock.move'].create({
    #             'name': _('New Move:') + move_line.product_id.display_name,
    #             'product_id': move_line.product_id.id,
    #             'product_uom_qty': move_line.qty_done,
    #             'product_uom': move_line.product_uom_id.id,
    #             'description_picking': move_line.description_picking,
    #             'location_id': move_line.picking_id.location_id.id,
    #             'location_dest_id': move_line.picking_id.location_dest_id.id,
    #             'picking_id': move_line.picking_id.id,
    #             'state': move_line.picking_id.state,
    #             'picking_type_id': move_line.picking_id.picking_type_id.id,
    #             'restrict_partner_id': move_line.picking_id.owner_id.id,
    #             'company_id': move_line.picking_id.company_id.id if move_line.picking_id.company_id.id else self.env.company.id,
    #         })
    #         move_line.move_id = new_move.id
    #         move_line.state = 'confirmed'
    #         new_move.state = 'confirmed'
    #
    #     for move_line in mls:
    #         # if move_line.picking_id.state != 'done':
    #         #     moves = move_line.picking_id.move_lines.filtered(lambda x: x.product_id == move_line.product_id)
    #         #     moves = sorted(moves, key=lambda m: m.quantity_done < m.product_qty, reverse=True)
    #         #     if moves and move_line.move_id.id == moves[0].id:
    #         #         create_move(move_line)
    #         #     else:
    #         #         create_move(move_line)
    #         # else:
    #         if move_line.qty_done and move_line.picking_id:
    #             create_move(move_line)

    @api.onchange("product_id", "product_uom_id")
    def _gen_domain(self):
        for finalize in self:
            if finalize.move_id.product_uom:
                lot_number = self.env['stock.lot'].search([('product_id', '=', finalize.product_id.id),
                                                           ('uom_id_2', '=', finalize.move_id.product_uom.id)]
                                                          ).ids
            else:
                lot_number = self.env['stock.lot'].search([('product_id', '=', finalize.product_id.id)]
                                                          ).ids
            return {'domain': {'lot_id': [('id', 'in', lot_number)]}}

    def _set_product_qty(self):
        """ The meaning of product_qty field changed lately and is now a functional field computing the quantity
        in the default product UoM. This code has been added to raise an error if a write is made given a value
        for `product_qty`, where the same write should set the `product_uom_qty` field instead, in order to
        detect errors. """
        pass
        # raise UserError(_('The requested operation cannot be processed because of a programming error setting the `product_qty` field instead of the `product_uom_qty`.'))


class StockMove(models.Model):
    _inherit = "stock.move"

    @api.depends('move_line_ids.product_qty')
    def _compute_reserved_availability(self):
        """ Fill the `availability` field on a stock move, which is the actual reserved quantity
        and is represented by the aggregated `product_qty` on the linked move lines. If the move
        is force assigned, the value will be 0.
        """
        if not any(self._ids):
            # onchange
            for move in self:
                reserved_availability = sum(move.move_line_ids.mapped('product_qty'))
                move.reserved_availability = move.product_id.uom_id._compute_quantity(
                    reserved_availability, move.product_uom, rounding_method='HALF-UP')
        else:
            # compute
            result = {data['move_id'][0]: data['product_qty'] for data in
                      self.env['stock.move.line'].read_group([('move_id', 'in', self.ids)], ['move_id', 'product_qty'],
                                                             ['move_id'])}
            for move in self:
                move.reserved_availability = move.product_id.uom_id._compute_quantity(
                    result.get(move.id, 0.0), move.product_uom, rounding_method='HALF-UP')

        # else:
        #     # compute
        #     result = {}
        #     for val in self:
        #         result = {data['move_id'][0]: data['product_qty'] for data in
        #                   self.env['stock.move.line'].read_group([('move_id', 'in', self.ids)],
        #                                                          ['move_id', 'product_qty'], ['move_id'])}
        #
        #         all_quants = self.env['stock.quant'].search([('product_id', '=', val.product_id.id),
        #                                                      ('uom_id_2', '=', val.product_uom.id),
        #                                                      ('location_id.usage', '=', 'internal')])
        #         total_qyt = 0
        #         for quant in all_quants:
        #             total_qyt += quant.available_quantity
        #         result[val.id] = total_qyt
        #
        #     for move in self:
        #         move.reserved_availability = move.product_id.uom_id._compute_quantity(
        #             result.get(move.id, 0.0), move.product_uom, rounding_method='HALF-UP')

    def _get_price_unit(self):
        """ Returns the unit price for the move"""
        self.ensure_one()
        if self.purchase_line_id and self.product_id.id == self.purchase_line_id.product_id.id:
            line = self.purchase_line_id
            order = line.order_id
            price_unit = line.price_unit
            if line.taxes_id:
                price_unit = \
                    line.taxes_id.with_context(round=False).compute_all(price_unit, currency=line.order_id.currency_id,
                                                                        quantity=1.0)['total_void']
            # if line.product_uom.id != line.product_id.uom_id.id:
            #     price_unit *= line.product_uom.factor / line.product_id.uom_id.factor
            if order.currency_id != order.company_id.currency_id:
                # The date must be today, and not the date of the move since the move move is still
                # in assigned state. However, the move date is the scheduled date until move is
                # done, then date of actual move processing. See:
                # https://github.com/odoo/odoo/blob/2f789b6863407e63f90b3a2d4cc3be09815f7002/addons/stock/models/stock_move.py#L36
                price_unit = order.currency_id._convert(
                    price_unit, order.company_id.currency_id, order.company_id, fields.Date.context_today(self),
                    round=False)
            return price_unit
        else:
            price_unit = self.price_unit
            # If the move is a return, use the original move's price unit.
            if self.origin_returned_move_id and self.origin_returned_move_id.sudo().stock_valuation_layer_ids:
                price_unit = self.origin_returned_move_id.stock_valuation_layer_ids[-1].unit_cost
            return not self.company_id.currency_id.is_zero(price_unit) and price_unit or self.product_id.standard_price

    # def _update_reserved_quantity(self, need, available_quantity, location_id, lot_id=None, package_id=None, owner_id=None, strict=True, uom_id=None):
    #     """ Create or update move lines.
    #     """
    #     self.ensure_one()
    #
    #     if not lot_id:
    #         lot_id = self.env['stock.lot']
    #     if not package_id:
    #         package_id = self.env['stock.quant.package']
    #     if not owner_id:
    #         owner_id = self.env['res.partner']
    #
    #     taken_quantity = min(available_quantity, need)
    #
    #     # `taken_quantity` is in the quants unit of measure. There's a possibility that the move's
    #     # unit of measure won't be respected if we blindly reserve this quantity, a common usecase
    #     # is if the move's unit of measure's rounding does not allow fractional reservation. We chose
    #     # to convert `taken_quantity` to the move's unit of measure with a down rounding method and
    #     # then get it back in the quants unit of measure with an half-up rounding_method. This
    #     # way, we'll never reserve more than allowed. We do not apply this logic if
    #     # `available_quantity` is brought by a chained move line. In this case, `_prepare_move_line_vals`
    #     # will take care of changing the UOM to the UOM of the product.
    #     if not strict:
    #         taken_quantity_move_uom = self.product_id.uom_id._compute_quantity(taken_quantity, self.product_uom, rounding_method='DOWN')
    #         taken_quantity = self.product_uom._compute_quantity(taken_quantity_move_uom, self.product_id.uom_id, rounding_method='HALF-UP')
    #
    #     quants = []
    #     rounding = self.env['decimal.precision'].precision_get('Product Unit of Measure')
    #
    #     if self.product_id.tracking == 'serial':
    #         if float_compare(taken_quantity, int(taken_quantity), precision_digits=rounding) != 0:
    #             taken_quantity = 0
    #
    #     try:
    #         with self.env.cr.savepoint():
    #             if not float_is_zero(taken_quantity, precision_rounding=self.product_id.uom_id.rounding):
    #                 # The below is the original code put by Usman, then we faced an error and we have to delete the last parameter
    #                 # quants = self.env['stock.quant']._update_reserved_quantity(
    #                 #     self.product_id, location_id, taken_quantity, lot_id=lot_id,
    #                 #     package_id=package_id, owner_id=owner_id, strict=strict, uom_id=uom_id
    #                 # )
    #                  quants = self.env['stock.quant']._update_reserved_quantity(
    #                     self.product_id, location_id, taken_quantity, lot_id=lot_id,
    #                     package_id=package_id, owner_id=owner_id, strict=strict
    #                 )
    #     except UserError:
    #         taken_quantity = 0
    #
    #     # Find a candidate move line to update or create a new one.
    #     for reserved_quant, quantity in quants:
    #         to_update = self.move_line_ids.filtered(lambda ml: ml._reservation_is_updatable(quantity, reserved_quant))
    #         if to_update:
    #             uom_quantity = self.product_id.uom_id._compute_quantity(quantity, to_update[0].product_uom_id, rounding_method='HALF-UP')
    #             uom_quantity = float_round(uom_quantity, precision_digits=rounding)
    #             uom_quantity_back_to_product_uom = to_update[0].product_uom_id._compute_quantity(uom_quantity, self.product_id.uom_id, rounding_method='HALF-UP')
    #         if to_update and float_compare(quantity, uom_quantity_back_to_product_uom, precision_digits=rounding) == 0:
    #             to_update[0].with_context(bypass_reservation_update=True).product_uom_qty += uom_quantity
    #         else:
    #             if self.product_id.tracking == 'serial':
    #                 for i in range(0, int(quantity)):
    #                     self.env['stock.move.line'].create(self._prepare_move_line_vals(quantity=1, reserved_quant=reserved_quant))
    #             else:
    #                 ll = self.env['stock.move.line'].create(self._prepare_move_line_vals(quantity=quantity, reserved_quant=reserved_quant))
    #                 if ll:
    #                     ll._compute_product_qty()
    #     return taken_quantity

    # def _action_assign(self):
    #     """ Reserve stock moves by creating their stock move lines. A stock move is
    #     considered reserved once the sum of `product_qty` for all its move lines is
    #     equal to its `product_qty`. If it is less, the stock move is considered
    #     partially available.
    #     """
    #     StockMove = self.env['stock.move']
    #     assigned_moves_ids = OrderedSet()
    #     partially_available_moves_ids = OrderedSet()
    #     # Read the `reserved_availability` field of the moves out of the loop to prevent unwanted
    #     # cache invalidation when actually reserving the move.
    #     reserved_availability = {move: move.quantity for move in self}
    #     roundings = {move: move.product_id.uom_id.rounding for move in self}
    #     move_line_vals_list = []
    #     for move in self.filtered(lambda m: m.state in ['confirmed', 'waiting', 'partially_available']):
    #         rounding = roundings[move]
    #         missing_reserved_uom_quantity = move.product_uom_qty - reserved_availability[move]
    #         missing_reserved_quantity = move.product_uom._compute_quantity(missing_reserved_uom_quantity, move.product_id.uom_id, rounding_method='HALF-UP')
    #         if move._should_bypass_reservation():
    #             # create the move line(s) but do not impact quants
    #             if move.product_id.tracking == 'serial' and (move.picking_type_id.use_create_lots or move.picking_type_id.use_existing_lots):
    #                 for i in range(0, int(missing_reserved_quantity)):
    #                     move_line_vals_list.append(move._prepare_move_line_vals(quantity=1))
    #             else:
    #                 to_update = move.move_line_ids.filtered(lambda ml: ml.product_uom_id == move.product_uom and
    #                                                         ml.location_id == move.location_id and
    #                                                         ml.location_dest_id == move.location_dest_id and
    #                                                         ml.picking_id == move.picking_id and
    #                                                         not ml.lot_id and
    #                                                         not ml.package_id and
    #                                                         not ml.owner_id)
    #                 if to_update:
    #                     to_update[0].product_uom_qty += missing_reserved_uom_quantity
    #                 else:
    #                     move_line_vals_list.append(move._prepare_move_line_vals(quantity=missing_reserved_quantity))
    #             assigned_moves_ids.add(move.id)
    #         else:
    #             if float_is_zero(move.product_uom_qty, precision_rounding=move.product_uom.rounding):
    #                 assigned_moves_ids.add(move.id)
    #             elif not move.move_orig_ids:
    #                 if move.procure_method == 'make_to_order':
    #                     continue
    #                 # If we don't need any quantity, consider the move assigned.
    #                 need = missing_reserved_quantity
    #                 if float_is_zero(need, precision_rounding=rounding):
    #                     assigned_moves_ids.add(move.id)
    #                     continue
    #                 # Reserve new quants and create move lines accordingly.
    #                 forced_package_id = move.package_level_id.package_id or None
    #                 available_quantity = move._get_available_quantity(move.location_id, package_id=forced_package_id)
    #                 if available_quantity <= 0:
    #                     continue
    #                 taken_quantity = move._update_reserved_quantity(need, available_quantity, move.location_id, package_id=forced_package_id, strict=False)
    #                 # The below is the original code put by Usman, then we faced an error and we have to delete the last parameter
    #                 # taken_quantity = move._update_reserved_quantity(need, available_quantity, move.location_id, package_id=forced_package_id, strict=False, uom_id=move.product_uom)
    #                 if float_is_zero(taken_quantity, precision_rounding=rounding):
    #                     continue
    #                 if float_compare(need, taken_quantity, precision_rounding=rounding) == 0:
    #                     assigned_moves_ids.add(move.id)
    #                 else:
    #                     partially_available_moves_ids.add(move.id)
    #             else:
    #                 # Check what our parents brought and what our siblings took in order to
    #                 # determine what we can distribute.
    #                 # `qty_done` is in `ml.product_uom_id` and, as we will later increase
    #                 # the reserved quantity on the quants, convert it here in
    #                 # `product_id.uom_id` (the UOM of the quants is the UOM of the product).
    #                 move_lines_in = move.move_orig_ids.filtered(lambda m: m.state == 'done').mapped('move_line_ids')
    #                 keys_in_groupby = ['location_dest_id', 'lot_id', 'result_package_id', 'owner_id']
    #
    #                 def _keys_in_sorted(ml):
    #                     return (ml.location_dest_id.id, ml.lot_id.id, ml.result_package_id.id, ml.owner_id.id)
    #
    #                 grouped_move_lines_in = {}
    #                 for k, g in groupby(sorted(move_lines_in, key=_keys_in_sorted), key=itemgetter(*keys_in_groupby)):
    #                     qty_done = 0
    #                     for ml in g:
    #                         qty_done += ml.qty_done
    #                     grouped_move_lines_in[k] = qty_done
    #                 move_lines_out_done = (move.move_orig_ids.mapped('move_dest_ids') - move)\
    #                     .filtered(lambda m: m.state in ['done'])\
    #                     .mapped('move_line_ids')
    #                 # As we defer the write on the stock.move's state at the end of the loop, there
    #                 # could be moves to consider in what our siblings already took.
    #                 moves_out_siblings = move.move_orig_ids.mapped('move_dest_ids') - move
    #                 moves_out_siblings_to_consider = moves_out_siblings & (StockMove.browse(assigned_moves_ids) + StockMove.browse(partially_available_moves_ids))
    #                 reserved_moves_out_siblings = moves_out_siblings.filtered(lambda m: m.state in ['partially_available', 'assigned'])
    #                 move_lines_out_reserved = (reserved_moves_out_siblings | moves_out_siblings_to_consider).mapped('move_line_ids')
    #                 keys_out_groupby = ['location_id', 'lot_id', 'package_id', 'owner_id']
    #
    #                 def _keys_out_sorted(ml):
    #                     return (ml.location_id.id, ml.lot_id.id, ml.package_id.id, ml.owner_id.id)
    #
    #                 grouped_move_lines_out = {}
    #                 for k, g in groupby(sorted(move_lines_out_done, key=_keys_out_sorted), key=itemgetter(*keys_out_groupby)):
    #                     qty_done = 0
    #                     for ml in g:
    #                         qty_done += ml.product_uom_id._compute_quantity(ml.qty_done, ml.product_id.uom_id)
    #                     grouped_move_lines_out[k] = qty_done
    #                 for k, g in groupby(sorted(move_lines_out_reserved, key=_keys_out_sorted), key=itemgetter(*keys_out_groupby)):
    #                     grouped_move_lines_out[k] = sum(self.env['stock.move.line'].concat(*list(g)).mapped('product_qty'))
    #                 available_move_lines = {key: grouped_move_lines_in[key] - grouped_move_lines_out.get(key, 0) for key in grouped_move_lines_in.keys()}
    #                 # pop key if the quantity available amount to 0
    #                 available_move_lines = dict((k, v) for k, v in available_move_lines.items() if v)
    #
    #                 if not available_move_lines:
    #                     continue
    #                 for move_line in move.move_line_ids.filtered(lambda m: m.product_qty):
    #                     if available_move_lines.get((move_line.location_id, move_line.lot_id, move_line.result_package_id, move_line.owner_id)):
    #                         available_move_lines[(move_line.location_id, move_line.lot_id, move_line.result_package_id, move_line.owner_id)] -= move_line.product_qty
    #                 for (location_id, lot_id, package_id, owner_id), quantity in available_move_lines.items():
    #                     need = move.product_qty - sum(move.move_line_ids.mapped('product_qty'))
    #                     # `quantity` is what is brought by chained done move lines. We double check
    #                     # here this quantity is available on the quants themselves. If not, this
    #                     # could be the result of an inventory adjustment that removed totally of
    #                     # partially `quantity`. When this happens, we chose to reserve the maximum
    #                     # still available. This situation could not happen on MTS move, because in
    #                     # this case `quantity` is directly the quantity on the quants themselves.
    #                     available_quantity = move._get_available_quantity(location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=True)
    #                     if float_is_zero(available_quantity, precision_rounding=rounding):
    #                         continue
    #                     taken_quantity = move._update_reserved_quantity(need, min(quantity, available_quantity), location_id, lot_id, package_id, owner_id)
    #                     # The below is the original code put by Usman, then we faced an error and we have to delete the last parameter
    #                     # taken_quantity = move._update_reserved_quantity(need, min(quantity, available_quantity), location_id, lot_id, package_id, owner_id, uom_id=move.product_uom)
    #                     if float_is_zero(
    #                         taken_quantity, precision_rounding=rounding):
    #                         continue
    #                     if float_is_zero(need - taken_quantity, precision_rounding=rounding):
    #                         assigned_moves_ids.add(move.id)
    #                         break
    #                     partially_available_moves_ids.add(move.id)
    #         if move.product_id.tracking == 'serial':
    #             move.next_serial_count = move.product_uom_qty
    #
    #     self.env['stock.move.line'].create(move_line_vals_list)
    #     StockMove.browse(partially_available_moves_ids).write({'state': 'partially_available'})
    #     StockMove.browse(assigned_moves_ids).write({'state': 'assigned'})
    #     self.mapped('picking_id')._check_entire_pack()

    # def _prepare_move_line_vals(self, quantity=None, reserved_quant=None):
    #     self.ensure_one()
    #     # apply putaway
    #     location_dest_id = self.location_dest_id._get_putaway_strategy(self.product_id).id or self.location_dest_id.id
    #     vals = {
    #         'move_id': self.id,
    #         'product_id': self.product_id.id,
    #         'product_uom_id': self.product_uom.id,
    #         'location_id': self.location_id.id,
    #         'location_dest_id': location_dest_id,
    #         'picking_id': self.picking_id.id,
    #         'company_id': self.company_id.id,
    #     }
    #     if quantity:
    #         rounding = self.env['decimal.precision'].precision_get('Product Unit of Measure')
    #         uom_quantity = self.product_id.uom_id._compute_quantity(quantity, self.product_uom, rounding_method='HALF-UP')
    #         uom_quantity = float_round(uom_quantity, precision_digits=rounding)
    #         uom_quantity_back_to_product_uom = self.product_uom._compute_quantity(uom_quantity, self.product_id.uom_id, rounding_method='HALF-UP')
    #         vals = dict(vals, product_uom_qty=self.product_uom_qty)
    #         # if float_compare(quantity, uom_quantity_back_to_product_uom, precision_digits=rounding) == 0:
    #         #     vals = dict(vals, product_uom_qty=uom_quantity)
    #         # else:
    #         #     vals = dict(vals, product_uom_qty=quantity, product_uom_id=self.product_id.uom_id.id)
    #     if reserved_quant:
    #         vals = dict(
    #             vals,
    #             location_id=reserved_quant.location_id.id,
    #             lot_id=reserved_quant.lot_id.id or False,
    #             package_id=reserved_quant.package_id.id or False,
    #             owner_id =reserved_quant.owner_id.id or False,
    #         )
    #     return vals

    # def _create_in_svl(self, forced_quantity=None):
    #     """Create a `stock.valuation.layer` from `self`.
    #
    #     :param forced_quantity: under some circunstances, the quantity to value is different than
    #         the initial demand of the move (Default value = None)
    #     """
    #     svl_vals_list = []
    #     for move in self:
    #         move = move.with_company(move.company_id)
    #         move.availability
    #         move.product_qty
    #         valued_move_lines = move._get_in_move_lines()
    #         valued_quantity = 0
    #         for valued_move_line in valued_move_lines:
    #             valued_quantity += valued_move_line.product_uom_id._compute_quantity(valued_move_line.qty_done, move.product_uom)
    #         unit_cost = abs(move._get_price_unit())  # May be negative (i.e. decrease an out move).
    #         if move.product_id.cost_method == 'standard':
    #             if move.product_uom.uom_type == 'bigger':
    #                 unit_cost = move.product_id.standard_price * move.product_uom.factor_inv
    #             elif move.product_uom.uom_type == 'smaller':
    #                 unit_cost = move.product_id.standard_price * move.product_uom.factor_inv
    #             else:
    #                 unit_cost = move.product_id.standard_price
    #         svl_vals = move.product_id._prepare_in_svl_vals(forced_quantity or valued_quantity, unit_cost)
    #         svl_vals.update(move._prepare_common_svl_vals())
    #         if forced_quantity:
    #             svl_vals['description'] = 'Correction of %s (modification of past move)' % move.picking_id.name or move.name
    #         svl_vals['uom_id_2'] = move.product_uom.id
    #         svl_vals['uom_id'] = move.product_uom.id
    #         svl_vals_list.append(svl_vals)
    #     return self.env['stock.valuation.layer'].sudo().create(svl_vals_list)

    def _create_out_svl(self, forced_quantity=None):
        """Create a `stock.valuation.layer` from `self`.

        :param forced_quantity: under some circunstances, the quantity to value is different than
            the initial demand of the move (Default value = None)
        """
        svl_vals_list = []
        for move in self:
            move = move.with_company(move.company_id)
            valued_move_lines = move._get_out_move_lines()
            valued_quantity = 0
            for valued_move_line in valued_move_lines:
                valued_quantity += valued_move_line.quantity
            if float_is_zero(forced_quantity or valued_quantity, precision_rounding=move.product_id.uom_id.rounding):
                continue
            svl_vals = move.product_id._prepare_out_svl_vals(forced_quantity or valued_quantity, move.company_id,
                                                             uom_id=move.product_uom)
            svl_vals.update(move._prepare_common_svl_vals())
            svl_vals['uom_id_2'] = move.product_uom.id
            svl_vals['uom_id'] = move.product_uom.id
            if forced_quantity:
                svl_vals[
                    'description'] = 'Correction of %s (modification of past move)' % move.picking_id.name or move.name
            svl_vals_list.append(svl_vals)
        return self.env['stock.valuation.layer'].sudo().create(svl_vals_list)
