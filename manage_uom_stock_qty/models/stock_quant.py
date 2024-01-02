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

    def stock_qty_adjustment(self):
        check_uom = self[0].product_uom_id.id
        check_product = self[0].product_id.id
        quant_adjustment = self.env['uom.quant.adjustment'].create({
            'selected_uom_id': check_uom,
            'product_id': check_product
        })
        for quant in self:
            if quant.product_uom_id.id != check_uom:
                raise UserError(_('You need to select same Unit Of Measure'))
            if quant.product_id.id != check_product:
                raise UserError(_('You need to select same Product'))
            self.env['uom.quant.adjustment.line'].create({
                'stock_quant_id': quant.id,
                'uom_quant_adjustment_id': quant_adjustment.id,
                'product_id': quant.product_id.id,
                'product_uom_id': quant.product_uom_id.id,
                'location_id': quant.location_id.id,
                'lot_id': quant.lot_id.id,
                'on_hand': quant.available_quantity,
            })
        return {
            'name': _('Qty UOM Adjustment'),
            'view_mode': 'form',
            # 'view_id': self.env.ref('manage_uom_stock_qty.uom_adjustment_form').id,
            'res_model': 'uom.quant.adjustment',
            'res_id': quant_adjustment.id,
            'type': 'ir.actions.act_window',
            "target": "new",
        }



