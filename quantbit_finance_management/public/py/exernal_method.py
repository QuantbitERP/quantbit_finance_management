import frappe

@frappe.whitelist()
def append_in_payment_reference(payment_advice):

    payment_advice_data = {}
    
    payment_advice_doc = frappe.get_doc("Payment Advice Entry", payment_advice)
    
    payment_advice_data["total_paidreceipt"] = payment_advice_doc.total_paidreceipt
    payment_advice_data["total_discount"] = payment_advice_doc.total_discount
    payment_advice_data["total_deduction"] = payment_advice_doc.total_deduction
    
    payment_advice_data["references"] = []
    
    for i in payment_advice_doc.get("payment_advice_details"):
        if i.check: 
            item_data = {
                "reference_doctype": i.type,
                "reference_name": i.reference_id,
                "total_amount": float(i.grand_total),
                "outstanding_amount": float(i.outstanding_amount),
                "allocated_amount": float(i.allocated_amount)
            }
            payment_advice_data["references"].append(item_data)
    
    return payment_advice_data
