# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models, fields
from odoo.tools.float_utils import float_round


class ReturnPickingInherit(models.TransientModel):
    _inherit = 'stock.return.picking'

    def _prepare_move_default_values(self, return_line, new_picking):
        vals = super(ReturnPickingInherit, self)._prepare_move_default_values(return_line, new_picking)
        vals['product_uom'] = return_line.uom_id.id
        return vals

    @api.model
    def _prepare_stock_return_picking_line_vals_from_move(self, stock_move):
        quantity = stock_move.product_qty
        for move in stock_move.move_dest_ids:
            if move.origin_returned_move_id and move.origin_returned_move_id != stock_move:
                continue
            if move.state in ('partially_available', 'assigned'):
                quantity -= sum(move.move_line_ids.mapped('product_qty'))
            elif move.state in ('done'):
                quantity -= move.product_qty
        quantity = float_round(quantity, precision_rounding=stock_move.product_uom.rounding)
        return {
            'product_id': stock_move.product_id.id,
            'quantity': quantity,
            'move_id': stock_move.id,
            'uom_id': stock_move.product_uom.id,
        }
