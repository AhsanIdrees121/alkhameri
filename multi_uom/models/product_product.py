# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from psycopg2 import Error, OperationalError

from odoo import _, api, fields, models
from datetime import timedelta, time


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _prepare_out_svl_vals(self, quantity, company, uom_id=None):
        """Prepare the values for a stock valuation layer created by a delivery.

        :param quantity: the quantity to value, expressed in `self.uom_id`
        :return: values to use in a call to create
        :rtype: dict
        """
        self.ensure_one()
        # Quantity is negative for out valuation layers.
        quantity = -1 * quantity
        vals = {
            'product_id': self.id,
            'value': quantity * self.standard_price if uom_id.uom_type == 'reference' else self.standard_price * uom_id.factor_inv * quantity,
            'unit_cost': self.standard_price,
            'quantity': quantity,
        }
        if self.cost_method in ('average', 'fifo'):
            fifo_vals = self._run_fifo(abs(quantity), company)
            vals['remaining_qty'] = fifo_vals.get('remaining_qty')
            # in case of AVCO, fix rounding issue of standard price when needed.
            if self.cost_method == 'average':
                rounding_error = self.standard_price * self.quantity_svl - self.value_svl
                vals['value'] += self.env.company.currency_id.round(rounding_error)
                if self.quantity_svl:
                    vals['unit_cost'] = self.value_svl / self.quantity_svl
            if self.cost_method == 'fifo':
                vals.update(fifo_vals)
        return vals

    # def _compute_sales_count(self):
        # r = {}
        # self.sales_count = 0
        # if not self.user_has_groups('sales_team.group_sale_salesman'):
        #     return r
        # date_from = fields.Datetime.to_string(fields.datetime.combine(fields.datetime.now() - timedelta(days=365),
        #                                                               time.min))
        #
        # done_states = self.env['sale.report']._get_done_states()
        #
        # domain = [
        #     ('state', 'in', done_states),
        #     ('product_id', 'in', self.ids),
        #     ('date', '>=', date_from),
        # ]
        # for sale in self.env['sale.report'].search(domain).order_id:
        #     for line in sale.order_line:
        #         if line.product_id.id:
        #             pass
        #
        # for group in self.env['sale.report'].read_group(domain, ['product_id', 'product_uom_qty'], ['product_id']):
        #     r[group['product_id'][0]] = group['product_uom_qty']
        # for product in self:
        #     if not product.id:
        #         product.sales_count = 0.0
        #         continue
        #     qty = 0.0
        #     for sale in self.env['sale.report'].search(domain).order_id:
        #         for line in sale.order_line:
        #             if line.product_id.id == product.id:
        #                 qty += line.uom_quantity
        #         product.sales_count = qty
        # return r
