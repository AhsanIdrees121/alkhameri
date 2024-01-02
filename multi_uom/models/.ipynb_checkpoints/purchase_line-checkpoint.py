# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.tools.float_utils import float_compare


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    def _prepare_stock_moves(self, picking):
        # res = super(PurchaseOrderLine, self)._prepare_stock_moves(picking)
        # for re in res:
        #     print()
        # return res
        """ Prepare the stock moves data for one order line. This function returns a list of
        dictionary ready to be used in stock.move's create()
        """
        self.ensure_one()
        res = []
        if self.product_id.type not in ['product', 'consu']:
            return res

        qty = 0.0
        price_unit = self._get_stock_move_price_unit()
        outgoing_moves, incoming_moves = self._get_outgoing_incoming_moves()
        for move in outgoing_moves:
            qty -= move.product_uom._compute_quantity(move.product_uom_qty, self.product_uom, rounding_method='HALF-UP')
        for move in incoming_moves:
            qty += move.product_uom._compute_quantity(move.product_uom_qty, self.product_uom, rounding_method='HALF-UP')

        move_dests = self.move_dest_ids
        if not move_dests:
            move_dests = self.move_ids.move_dest_ids.filtered(lambda m: m.state != 'cancel' and not m.location_dest_id.usage == 'supplier')

        if not move_dests:
            qty_to_attach = 0
            qty_to_push = self.product_qty - qty
        else:
            move_dests_initial_demand = self.product_id.uom_id._compute_quantity(
                sum(move_dests.filtered(lambda m: m.state != 'cancel' and not m.location_dest_id.usage == 'supplier').mapped('product_qty')),
                self.product_uom, rounding_method='HALF-UP')
            qty_to_attach = move_dests_initial_demand - qty
            qty_to_push = self.product_qty - move_dests_initial_demand

        if float_compare(qty_to_attach, 0.0, precision_rounding=self.product_uom.rounding) > 0:
            product_uom_qty, product_uom = self.product_uom._adjust_uom_quantities(qty_to_attach, self.product_uom)
            res.append(self._prepare_stock_move_vals(picking, price_unit, product_uom_qty, product_uom))
        if float_compare(qty_to_push, 0.0, precision_rounding=self.product_uom.rounding) > 0:
            # product_uom_qty, product_uom = self.product_uom._adjust_uom_quantities(qty_to_push, self.product_id.uom_id)
            product_uom_qty, product_uom = self.product_uom._adjust_uom_quantities(qty_to_push, self.product_uom)
            extra_move_vals = self._prepare_stock_move_vals(picking, price_unit, product_uom_qty, product_uom)
            extra_move_vals['move_dest_ids'] = False  # don't attach
            res.append(extra_move_vals)
        return res
