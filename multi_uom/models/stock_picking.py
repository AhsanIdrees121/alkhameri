
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):
        # OVERRIDE to check the consistency of the statement's state regarding the session's state.
        for stock_pick in self:
            check = False
            check_package = False
            purchase_id = self.env['purchase.order'].search([('name', '=', stock_pick.origin)])

            if stock_pick.sale_id or purchase_id:
                for stock in stock_pick.move_ids_without_package:
                    for stock_line in stock.move_line_ids:
                        if stock_line.product_id.tracking == 'lot':
                            if not stock_line.lot_id:
                                check_package = True
                            else:
                                if stock_line.product_uom_id.id != stock_line.lot_id.product_uom_id.id:
                                    raise UserError(_("Your lot number %s UOM and Line UOM is not matched"%(stock_line.lot_id.name)))
            else:
                for stock_line in stock_pick.move_line_nosuggest_ids:
                    if not stock_line.product_id.tracking == 'lot':
                        if not stock_line.lot_name:
                            check = True

            if check_package and check:
                raise UserError(_("You didn't add a lot with your product kindly add it"))
        return super(StockPicking, self).button_validate()
