from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import pandas as pd
import os
from datetime import datetime

app = FastAPI(title="Meesho Seller Analytics API")

ASSETS_DIR = "assets"
os.makedirs(ASSETS_DIR, exist_ok=True)

@app.post("/upload-order-file/")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.endswith('.xlsx'):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported.")

    file_location = os.path.join(ASSETS_DIR, file.filename)
    with open(file_location, "wb") as f:
        content = await file.read()
        f.write(content)

    return {"filename": file.filename, "message": "File uploaded successfully."}

@app.get("/order-payments/summary")
def get_order_summary():
    try:
        file_paths = [
            os.path.join(ASSETS_DIR, f)
            for f in os.listdir(ASSETS_DIR)
            if f.endswith(".xlsx")
        ]

        combined_df = pd.DataFrame()
        for path in file_paths:
            df = pd.read_excel(path, sheet_name="Order Payments", header=1)
            combined_df = pd.concat([combined_df, df], ignore_index=True)

        df = combined_df.where(pd.notnull(combined_df), None)
        df.drop_duplicates(subset=["Sub Order No"], inplace=True)

        df['Payment Date'] = pd.to_datetime(df['Payment Date'], errors='coerce')
        df = df[(df['Payment Date'] >= '2025-04-02') & (df['Payment Date'] <= '2025-06-24')]
        df['Payment Month'] = df['Payment Date'].dt.to_period("M").astype(str)

        settlement_col = 'Final Settlement Amount'
        return_col = 'Total Sale Return Amount (Incl. Shipping & GST)'
        shipping_col = 'Return Shipping Charge (Incl. GST)'
        claims_col = 'Claims'
        ads_cost_col = 'Ads Cost' if 'Ads Cost' in df.columns else None

        for col in [settlement_col, return_col, shipping_col, claims_col]:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        if ads_cost_col:
            df[ads_cost_col] = pd.to_numeric(df[ads_cost_col], errors='coerce')

        total_orders = len(df)
        total_settlement_amount = df[settlement_col].sum()
        total_ads_cost = df[ads_cost_col].sum() if ads_cost_col else 0.0

        return_statuses = ['RTO', 'Return', 'Shipped']
        return_df = df[df['Live Order Status'].isin(return_statuses)]
        return_count = len(return_df)

        product_return_amount = return_df[return_col].sum()
        customer_return_df = df[df['Live Order Status'].isin(['Return', 'Shipped'])]
        customer_shipping_charge = customer_return_df[shipping_col].sum()
        total_return_amount = product_return_amount + customer_shipping_charge

        customer_return_count = len(customer_return_df)
        customer_return_amount = customer_return_df[return_col].sum() + customer_shipping_charge

        rto_df = df[df['Live Order Status'] == 'RTO']
        rto_count = len(rto_df)
        rto_amount = rto_df[return_col].sum()

        claims_df = df[df[claims_col] > 0]
        claims_count = len(claims_df)
        claims_amount = claims_df[claims_col].sum()

        grouped = df.groupby('Product Name')
        productwise = []

        for name, group in grouped:
            product_total_orders = len(group)
            product_settlement = group[settlement_col].sum()

            product_return_df = group[group['Live Order Status'].isin(return_statuses)]
            product_return_count = len(product_return_df)
            product_return_amount = product_return_df[return_col].sum()

            product_customer_df = group[group['Live Order Status'].isin(['Return', 'Shipped'])]
            product_shipping_charge = product_customer_df[shipping_col].sum()

            product_claims_df = group[group[claims_col] > 0]
            product_claims_count = len(product_claims_df)
            product_claims_amount = product_claims_df[claims_col].sum()

            productwise.append({
                "product_name": name,
                "total_orders": product_total_orders,
                "total_settlement_amount": round(product_settlement, 2),
                "return_count": product_return_count,
                "return_amount": round(product_return_amount + product_shipping_charge, 2),
                "customer_shipping_charge": round(product_shipping_charge, 2),
                "claims_count": product_claims_count,
                "claims_amount": round(product_claims_amount, 2)
            })

        # External constants from PDF
        cost_of_goods_sold = 2940770.00
        gst_payable = 55482.10
        tds = -4315.04
        other_charges = -1198.40

        # Correct logic based on other software
        shipping_cost = -(customer_shipping_charge + rto_amount)
        sales_excl_gst = total_settlement_amount
        sales_less_expenses = sales_excl_gst + shipping_cost + other_charges + (-total_ads_cost)
        gross_profit = sales_less_expenses - cost_of_goods_sold
        gross_profit_percent = (gross_profit / sales_excl_gst * 100) if sales_excl_gst else 0

        net_amount_received = sales_less_expenses - gst_payable + claims_amount + tds
        avg_payment_cycle_days = 15.05

        quantity_analysis = {
            "sales_qty": total_orders,
            "customer_return_qty": -customer_return_count,
            "rto_return_qty": -rto_count,
            "net_sales_qty": total_orders - customer_return_count - rto_count
        }

        neft_summary = df.groupby('Payment Date')[settlement_col].sum().reset_index()
        neft_summary = [
            {
                "payment_date": row['Payment Date'].strftime("%Y-%m-%d"),
                "final_settlement_amount": round(row[settlement_col], 2),
                "ads_amount": 0.0,
                "total_amount": round(row[settlement_col], 2)
            }
            for _, row in neft_summary.iterrows()
        ]

        return {
            "calculation_of_gross_profit": {
                "sales_excl_gst": round(sales_excl_gst, 2),
                "commission": 0.0,
                "shipping": round(shipping_cost, 2),
                "other_charges": round(other_charges, 2),
                "ads_cost": round(-total_ads_cost, 2),
                "sales_less_expenses": round(sales_less_expenses, 2),
                "non_refundable_gst": 0.0,
                "cost_of_goods_sold": round(cost_of_goods_sold, 2),
                "gross_profit": round(gross_profit, 2),
                "gross_profit_percent": round(gross_profit_percent, 2)
            },
            "funds_flow_analysis": {
                "sales_less_expenses": round(sales_less_expenses, 2),
                "non_refundable_gst": 0.0,
                "refundable_gst": 0.0,
                "gst_payable": round(gst_payable, 2),
                "tds": round(tds, 2),
                "claims_from_meesho": round(claims_amount, 2),
                "net_amount_received": round(net_amount_received, 2),
                "average_payment_cycle_days": avg_payment_cycle_days
            },
            "quantity_analysis": quantity_analysis,
            "neft_wise_payment_summary": neft_summary,
            "productwise": productwise
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing summary: {str(e)}")