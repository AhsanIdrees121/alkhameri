# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from psycopg2 import Error, OperationalError

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression
from odoo.tools.float_utils import float_compare, float_is_zero, float_round

_logger = logging.getLogger(__name__)


class UomQuantAdjustment(models.Model):
    _name = 'uom.quant.adjustment'

    product_id = fields.Many2one('product.product')
    name = fields.Char('Description')
    selected_uom_id = fields.Many2one('uom.uom', string='Selected UOM')
    product_uom_category_id = fields.Many2one(related='product_id.uom_id.category_id')
    converted_uom_id = fields.Many2one('uom.uom', string='Converted UOM',
                                       domain="[('category_id', '=', product_uom_category_id)]")
    location_id = fields.Many2one(
        'stock.location', 'Source Location',
        domain="[('usage','=','internal')]")

    exiting_lot = fields.Boolean('Existing Lot #')
    exist_lot_id = fields.Many2one('stock.lot', string='Existing Lot')
    new_lot_id = fields.Char('New Lot Number')
    changing_value = fields.Float('Qty Converted UOM', compute='_compute_quantity')
    uom_adjustment_line = fields.One2many('uom.quant.adjustment.line', 'uom_quant_adjustment_id',
                                          string='Adjustment Line')
    validation_message = fields.Char('Validation Message')

    @api.onchange('converted_uom_id', 'exiting_lot')
    def exit_lot_number_domain(self):
        self.exist_lot_id = False
        if self.converted_uom_id and self.exiting_lot and self.converted_uom_id.id == self.selected_uom_id.id:
            neglect_lot_ids = []
            for adjustment_line in self.uom_adjustment_line:
                neglect_lot_ids.append(adjustment_line.lot_id.id)
            lot_number = self.env['stock.lot'].search([('product_id', '=', self.product_id.id),
                                                                  ('id', 'not in', neglect_lot_ids),
                                                                  ('uom_id_2', '=', self.converted_uom_id.id)]
                                                                 ).ids

            return {'domain': {'exist_lot_id': [('id', 'in', lot_number)]}}

        elif self.converted_uom_id and self.exiting_lot:
            lot_number = self.env['stock.lot'].search([('product_id', '=', self.product_id.id),
                                                                  ('uom_id_2', '=', self.converted_uom_id.id)]
                                                                 ).ids
            return {'domain': {'exist_lot_id': [('id', 'in', lot_number)]}}

        else:
            return {'domain': {'exist_lot_id': [('id', 'in', [])]}}

    @api.depends('uom_adjustment_line.counted')
    @api.onchange('converted_uom_id')
    def _compute_quantity(self):
        for val in self:
            if not val.converted_uom_id:
                val.changing_value = 0
                return

            line_qty = 0
            for line in val.uom_adjustment_line:
                line_qty += line.counted
            if not line_qty:
                val.changing_value = 0
                return

            if val.selected_uom_id.factor_inv > val.converted_uom_id.factor_inv:
                line_qty = val.selected_uom_id.factor_inv / val.converted_uom_id.factor_inv * line_qty
            elif val.selected_uom_id.factor_inv < val.converted_uom_id.factor_inv:
                line_qty = val.selected_uom_id.factor_inv / val.converted_uom_id.factor_inv * line_qty
            val.changing_value = line_qty

            if line_qty != int(line_qty):
                val.validation_message = 'You Need To Convert Full Qty To UOM'
            elif line_qty == int(line_qty):
                val.validation_message = 'You Can Convert it Successfully'

    def confirm_action(self):

        for adjustment_line in self.uom_adjustment_line:
            if not adjustment_line.counted:
                raise UserError(_("You didn't add any count value on %s lot number count" % (
                    adjustment_line.lot_id.name)))

            if adjustment_line.counted > adjustment_line.on_hand:
                raise UserError(_("You can't make count value greater then on hand, on %s lot number" % (
                    adjustment_line.lot_id.name)))

        if self.validation_message == 'You Need To Convert Full Qty To UOM':
            raise UserError(_("You can't confirm it because you need to convert full qty to %s UOM"%(self.converted_uom_id.name)))
        if self.exiting_lot:
            if self.exist_lot_id.product_uom_id != self.converted_uom_id:
                raise UserError(
                    _('You existing lot number should be same UOM'))
        # stock_inventory_id = self.env['stock.inventory'].create(
        #     {
        #         'name': str(self.product_id.name) + ' - ' + self.selected_uom_id.name + ' to '
        #                 + self.converted_uom_id.name + ' at ' + str(fields.Datetime.now()),
        #         'product_ids': self.product_id.ids,
        #         'prefill_counted_quantity': 'counted'
        #     })
        # stock_inventory_id.action_start()
        # all_line_ids = stock_inventory_id.line_ids
        for line in self.uom_adjustment_line:
            stock_id = self.env['stock.quant'].search([('location_id.id','=',line.location_id.id),
                                                       ('product_uom_id.id','=',line.product_uom_id.id),
                                                       ('product_id.id','=',line.product_id.id),
                                                       ('lot_id.id','=',line.lot_id.id)])
            stock_id.inventory_quantity = stock_id.quantity - line.counted
            stock_id.action_apply_inventory()

        if self.exiting_lot:
            stock_quant_id = self.env['stock.quant'].search([('location_id.id','=',self.location_id.id),
                                                       ('product_uom_id.id','=',self.selected_uom_id.id),
                                                       ('product_id.id','=',self.product_id.id),
                                                       ('lot_id.id','=',self.exist_lot_id.id)])
            if stock_quant_id:
                stock_quant_id.inventory_quantity = stock_quant_id.quantity + self.changing_value
            if not stock_quant_id:
                stock_quant_id = self.env['stock.quant'].create({
                    'location_id': self.location_id.id,
                    'product_id': self.product_id.id,
                    'lot_id': self.exist_lot_id.id,
                    'inventory_quantity': self.changing_value,
                    'uom_id_2': self.converted_uom_id.id,
                })

            # valuation_line.product_qty = valuation_line.product_qty + self.changing_value
        else:
            lot_id = self.env['stock.lot'].create({
                'company_id': self.env.user.company_id.id,
                'name': self.new_lot_id,
                'product_id': self.product_id.id,
                'product_qty': self.changing_value,
                'product_uom_id': self.converted_uom_id.id,
                'uom_id_2': self.converted_uom_id.id,
            })
            stock_quant_id = self.env['stock.quant'].create({
                'location_id': self.location_id.id,
                'product_id': self.product_id.id,
                'lot_id': lot_id.id,
                'inventory_quantity': self.changing_value,
                'uom_id_2': self.converted_uom_id.id,
            })
        stock_quant_id.action_apply_inventory()
        # stock_inventory_id.action_validate()


class UomQuantAdjustmentLine(models.Model):
    _name = 'uom.quant.adjustment.line'

    uom_quant_adjustment_id = fields.Many2one('uom.quant.adjustment')
    product_id = fields.Many2one('product.product', 'Product')
    product_uom_id = fields.Many2one('uom.uom', 'Unit of Measure')
    location_id = fields.Many2one('stock.location', 'Location')
    lot_id = fields.Many2one('stock.lot', 'Lot/Serial Number')
    on_hand = fields.Float('On Hand ')
    counted = fields.Float('Counted')
    stock_quant_id = fields.Many2one('stock.quant')

    # @api.onchange('counted')
    # def _compute_parent_quantity(self):
    #     if self.uom_quant_adjustment_id:
    #         self.uom_quant_adjustment_id._compute_quantity()
