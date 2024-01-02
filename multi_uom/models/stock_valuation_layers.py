# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, tools, api


class StockLot(models.Model):
    _inherit = 'stock.lot'

    product_uom_id = fields.Many2one('uom.uom', related=False, compute='_get_uom_by_second_unit', readonly=True,
                                     store=True, required=False)
    uom_id_2 = fields.Many2one('uom.uom', string='UOM 2')
    product_qty_2 = fields.Float('Other Qty')

    # def create(self, vals):
    #     res = super(StockLot, self).create(vals)
    #     res.uom_id_2 = res.product_uom_id
    #     return res

    @api.depends('uom_id_2')
    @api.onchange('uom_id_2')
    def _get_uom_by_second_unit(self):
        print('-XYZ-')
        for val in self:
            if val.uom_id_2:
                val.product_uom_id = val.uom_id_2.id
            else:
                val.product_uom_id = val.product_id.uom_id.id


class StockValuationLayer(models.Model):
    """Stock Valuation Layer"""

    _inherit = 'stock.valuation.layer'

    uom_id = fields.Many2one('uom.uom', related=False, compute='_get_uom_by_second_unit', readonly=True, required=True)
    uom_id_2 = fields.Many2one('uom.uom', string='UOM 2')

    @api.depends('uom_id_2')
    @api.onchange('uom_id_2')
    def _get_uom_by_second_unit(self):
        for val in self:
            if val.uom_id_2:
                val.uom_id = val.uom_id_2.id
            else:
                val.uom_id = val.product_id.uom_id.id
