import re

def extract_all_amounts(text):
    patterns = [
        (r'Наличные|Наличными', 'cash'),
        (r'Терминал', 'terminal'),
        (r'П[\\/]О|ПО', 'prepayment'),
        (r'QR[- ]?код|QR\s*код|QRCode|QrCode|QR\s*Code', 'qr'),
        (r'Рассрочка', 'installment'),
    ]
    results = []
    number_pattern = r'(\d[\d\s]*(?:[.,]\d+)?)'
    for kw, typ in patterns:
        for match in re.finditer(rf'(?:{kw})\s*[-–—]?\s*{number_pattern}', text, re.IGNORECASE):
            num_str = match.group(1).replace(' ', '').replace(',', '.')
            try:
                amount = float(num_str)
                results.append((typ, amount))
            except:
                continue
        for match in re.finditer(rf'{number_pattern}\s*[-–—]?\s*(?:{kw})', text, re.IGNORECASE):
            num_str = match.group(1).replace(' ', '').replace(',', '.')
            try:
                amount = float(num_str)
                results.append((typ, amount))
            except:
                continue
    return results

def extract_preorder_amounts(lines):
    cash = terminal = qr = installment = 0.0
    for line in lines:
        amounts = extract_all_amounts(line)
        for typ, val in amounts:
            if typ == 'cash':
                cash += val
            elif typ == 'terminal':
                terminal += val
            elif typ == 'qr':
                qr += val
            elif typ == 'installment':
                installment += val
    return cash, terminal, qr, installment

def extract_sales_amounts(lines):
    cash = terminal = qr = installment = 0.0
    for line in lines:
        amounts = extract_all_amounts(line)
        for typ, val in amounts:
            if typ == 'prepayment':
                continue
            if typ == 'cash':
                cash += val
            elif typ == 'terminal':
                terminal += val
            elif typ == 'qr':
                qr += val
            elif typ == 'installment':
                installment += val
    return cash, terminal, qr, installment
