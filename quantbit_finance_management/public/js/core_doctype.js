frappe.ui.form.on('Payment Entry', {
	setup: function (frm) {
		frm.set_query("custom_payment_advice", function (doc) {
			return {
				filters: [ 
                    ['Payment Advice Entry', 'payment_type', '=', frm.doc.payment_type],
                    ['Payment Advice Entry', 'party_type', '=', frm.doc.party_type],
                    ['Payment Advice Entry', 'party', '=', frm.doc.party],
                    ['Payment Advice Entry', 'docstatus', '=', 1],
				]
			};
		});
	},
    custom_payment_advice: async function(frm){
        await frappe.call({
            method: "quantbit_finance_management.public.py.exernal_method.append_in_payment_reference",
            args:{
                payment_advice:frm.doc.custom_payment_advice,
            },
            callback: function(response) {
                if (!response.exc) {
                    frm.clear_table("references");
                    discount_amount = response.message.total_discount
                    deduction_amount = response.message.total_deduction
                    frm.set_value("paid_amount", response.message.total_paidreceipt);
                    response.message.references.forEach(item => {
                        let row = frappe.model.add_child(frm.doc, "Payment Entry Reference", "references");
                        row.reference_doctype = item.reference_doctype;
                        row.reference_name = item.reference_name;
                        row.total_amount=item.total_amount;
                        row.outstanding_amount = item.outstanding_amount;
                        row.allocated_amount = item.allocated_amount;
                    });
                    if(discount_amount)
                        {
                            var c = frappe.model.add_child(frm.doc, "Payment Entry Deduction", "deductions");
                            c.amount =frm.doc.party_type=="Supplier" ? - discount_amount: discount_amount;
                            frappe.model.get_value('Finance Setting', {'name': 'Finance Setting'}, 'default_discount_account',
                            function(d) {
                                c.account = d.default_discount_account;
                            })
                            frm.refresh_field('deductions');
                        }
                    if(deduction_amount)
                        {
                            if(frm.doc.party_type!="Supplier")
                            {
                                var e=frappe.model.add_child(frm.doc, "Payment Entry Deduction", "deductions");
                                e.amount = (deduction_amount || 0);
                                frappe.model.get_value('Finance Setting', {'name': 'Finance Setting'}, 'default_deduction_account',
                                function(d) {
                                    e.account = parseFloat(d.default_deduction_account);
                                })
                                frm.refresh_field('deductions');
                            }        
                        }
                    frm.refresh();
                    
                } else {
                    frappe.msgprint("Error: " + response.exc);
                }
            }
         })
    },

});
