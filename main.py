from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import pandas as pd
import os

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
    files = [f for f in os.listdir(ASSETS_DIR) if f.endswith('.xlsx')]
    if not files:
        raise HTTPException(status_code=404, detail="No Excel file found in assets directory.")

    filepath = os.path.join(ASSETS_DIR, files[0])

    try:
        df = pd.read_excel(filepath, sheet_name="Order Payments", header=1)
        df = df.where(pd.notnull(df), None)

        # ✅ Use exact column names from file
        settlement_col = 'Final Settlement Amount'
        return_col = 'Sale Return Amount (Incl. GST)'
        shipping_col = 'Return Shipping Charge (Excl. GST)'
        claims_col = 'Claims'

        # Convert necessary fields
        for col in [settlement_col, return_col, shipping_col, claims_col]:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        total_orders = len(df)
        total_settlement_amount = df[settlement_col].sum()

        # Return logic
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

        # Product-wise breakdown
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

        return {
            "total_orders": total_orders,
            "total_settlement_amount": round(total_settlement_amount, 2),
            "return_rate_percent": round((return_count / total_orders) * 100, 2) if total_orders else 0,

            "total_return_count": return_count,
            "total_return_amount": round(total_return_amount, 2),

            "claims_success_count": claims_count,
            "claims_amount": round(claims_amount, 2),

            "customer_return_count": customer_return_count,
            "customer_return_amount": round(customer_return_amount, 2),
            "customer_return_shipping_charge": round(customer_shipping_charge, 2),

            "rto_count": rto_count,
            "rto_amount": round(rto_amount, 2),

            "productwise": productwise
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing summary: {str(e)}")
