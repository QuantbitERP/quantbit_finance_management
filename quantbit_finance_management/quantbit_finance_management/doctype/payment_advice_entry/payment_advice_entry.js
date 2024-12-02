// Copyright (c) 2024, Quantbit Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Payment Advice Entry", {
// 	refresh(frm) {

// 	},
// });

// Reusable method for calling the server-side function
async function call_method(frm, functionName) {
    await frm.call({
        method: functionName,
        doc: frm.doc
    });
}

frappe.ui.form.on('Payment Advice Entry', {
	setup: function (frm) {
		frm.set_query("party_type", function (doc) {
			return {
				filters: [
					['DocType', 'name', 'in', ['Customer', 'Supplier', 'Shareholder', 'Employee']]
				]
			};
		});
	},
    party: async function(frm) {
        frm.clear_table("payment_advice_details")
        frm.clear_table("deductions")
        frm.refresh_field("payment_advice_details");
        frm.refresh_field("deductions");
        if (frm.doc.payment_type != 'Internal Transfer'){
            await call_method(frm, 'get_payment_references');
        }
    },
    discount_rate: async function(frm) {
        await call_method(frm, 'calculation_on_discount_rate');
	},
    deduction_rate: async function(frm) {
        await call_method(frm, 'calculation_on_deduction_rate');
	},
    discount_on_base_total: async function(frm) {
        await call_method(frm, 'calculation_on_discount_on_base_total');
	},
    // add_references: async function(frm){
    //     await call_method(frm, 'calculation_on_deduction_rate');            
    // } calculation_on_deduction
});

frappe.ui.form.on("Payment Advice Entry Details", {
    discount_amount: async function(frm) {
        await call_method(frm, 'calculation_on_discount');
	},
    deduction_amount: async function(frm) {
        await call_method(frm, 'calculation_on_deduction');
	},
    allocated_amount: async function(frm) {
        await call_method(frm, 'calculate_total_fields');
	},
    check: async function(frm,cdt,cdn) {
        let d = locals[cdt][cdn];
        await call_method(frm, 'calculation_on_check');
	},
});