Run pytest tests/ -v --cov=bot --cov=web_admin --cov-report=xml
============================= test session starts ==============================
platform linux -- Python 3.11.15, pytest-8.2.0, pluggy-1.6.0 -- /opt/hostedtoolcache/Python/3.11.15/x64/bin/python
cachedir: .pytest_cache
rootdir: /home/runner/work/telegram-bot/telegram-bot
configfile: pytest.ini
plugins: asyncio-0.23.6, cov-5.0.0, anyio-4.13.0
asyncio: mode=Mode.AUTO
collecting ... collected 21 items / 1 error

==================================== ERRORS ====================================
___________ ERROR collecting tests/integration/test_preorder_flow.py ___________
ImportError while importing test module '/home/runner/work/telegram-bot/telegram-bot/tests/integration/test_preorder_flow.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/opt/hostedtoolcache/Python/3.11.15/x64/lib/python3.11/site-packages/_pytest/python.py:487: in importtestmodule
    mod = import_path(
/opt/hostedtoolcache/Python/3.11.15/x64/lib/python3.11/site-packages/_pytest/pathlib.py:591: in import_path
    importlib.import_module(module_name)
/opt/hostedtoolcache/Python/3.11.15/x64/lib/python3.11/importlib/__init__.py:126: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
<frozen importlib._bootstrap>:1204: in _gcd_import
    ???
<frozen importlib._bootstrap>:1176: in _find_and_load
    ???
<frozen importlib._bootstrap>:1147: in _find_and_load_unlocked
    ???
<frozen importlib._bootstrap>:690: in _load_unlocked
    ???
/opt/hostedtoolcache/Python/3.11.15/x64/lib/python3.11/site-packages/_pytest/assertion/rewrite.py:178: in exec_module
    exec(co, module.__dict__)
tests/integration/test_preorder_flow.py:5: in <module>
    from bot.repositories.item import ItemRepository
bot/repositories/__init__.py:2: in <module>
    from .item import ItemRepository
bot/repositories/item.py:7: in <module>
    from bot.utils.validators import extract_serials
bot/utils/__init__.py:2: in <module>
    from .parser import extract_payment_amounts, parse_client_data
bot/utils/parser.py:6: in <module>
    from bot.services.payment_parser import (
bot/services/__init__.py:2: in <module>
    from .assortment import AssortmentService
bot/services/assortment.py:4: in <module>
    from bot.repositories import ItemRepository
E   ImportError: cannot import name 'ItemRepository' from partially initialized module 'bot.repositories' (most likely due to a circular import) (/home/runner/work/telegram-bot/telegram-bot/bot/repositories/__init__.py)
=============================== warnings summary ===============================
../../../../../opt/hostedtoolcache/Python/3.11.15/x64/lib/python3.11/site-packages/_pytest/config/__init__.py:1448
  /opt/hostedtoolcache/Python/3.11.15/x64/lib/python3.11/site-packages/_pytest/config/__init__.py:1448: PytestConfigWarning: Unknown config option: asyncio_loop_scope
  
    self._warn_or_fail_if_strict(f"Unknown config option: {key}\n")

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html

---------- coverage: platform linux, python 3.11.15-final-0 ----------
Name                                Stmts   Miss  Cover   Missing
-----------------------------------------------------------------
bot/__init__.py                         0      0   100%
bot/background.py                      60     60     0%   2-107
bot/config.py                          25      1    96%   11
bot/db.py                             128    109    15%   18-35, 45-69, 74-77, 82-269, 274-280, 285-294
bot/handlers/__init__.py               31      8    74%   13-14, 20-21, 30-31, 37-38
bot/handlers/admin_migration.py         4      0   100%
bot/handlers/base.py                   32     17    47%   18-30, 33-67, 70-71, 75
bot/handlers/callbacks.py             169    135    20%   30-33, 38-53, 64-105, 116-121, 132-140, 153-207, 212-278
bot/handlers/commands.py              350    293    16%   25, 29-41, 45, 49-50, 61, 66-94, 98-125, 129-179, 183-219, 224-244, 248-269, 280-310, 321-357, 368-376, 389-417, 428-453, 465-489, 494-501, 506-531, 536-562
bot/handlers/states.py                  5      0   100%
bot/handlers/topics/__init__.py         5      0   100%
bot/handlers/topics/arrival.py        176    149    15%   27-64, 73-235, 240-284, 289-290, 302
bot/handlers/topics/assortment.py      73     56    23%   25-68, 76-98
bot/handlers/topics/common.py          23     14    39%   15-34
bot/handlers/topics/preorder.py        63     48    24%   26-108
bot/handlers/topics/sales.py           58     41    29%   27-33, 42-97
bot/models.py                         120    120     0%   2-172
bot/repositories/__init__.py            4      0   100%
bot/repositories/client.py            103     81    21%   24-86, 97-111, 116-119, 124-131, 136-149, 154-186
bot/repositories/item.py              171    124    27%   18-24, 28-45, 51-61, 69-79, 84-102, 108-125, 130-138, 143-151, 159-167, 172-175, 180-187, 195-211, 216-219, 224-260
bot/repositories/stats.py              43     25    42%   25-34, 43-45, 53-55, 62-102, 129-135
bot/services/__init__.py                5      0   100%
bot/services/assortment.py             58     43    26%   15-16, 20-34, 38-40, 44-96
bot/services/booking.py                40     31    22%   18-58
bot/services/cache.py                  64     44    31%   23, 26-34, 37-42, 45-50, 53-60, 65-74, 77-81
bot/services/message_service.py        22     14    36%   18-30, 38-49, 54-60
bot/services/payment.py                17      9    47%   22-30, 38-40
bot/services/payment_parser.py         45     36    20%   21, 25-61, 65-70
bot/services/sale.py                   29     21    28%   14-68
bot/utils/__init__.py                   5      0   100%
bot/utils/helpers.py                   18     11    39%   28-49
bot/utils/markdown.py                   7      4    43%   9-10, 17-18
bot/utils/parser.py                    96     85    11%   22-40, 44-146
bot/utils/sort.py                     202    187     7%   6, 10, 14-17, 21-24, 28-33, 41-42, 49-59, 63-121, 124-129, 132-133, 136-187, 190-212, 215-233, 236-262
bot/utils/validators.py                21     18    14%   6-20, 23-25
bot/webhook_utils.py                   26     26     0%   2-35
web_admin/__init__.py                   0      0   100%
web_admin/auth.py                      19     19     0%   2-26
web_admin/generate_hash.py              6      6     0%   6-13
web_admin/main.py                      29     29     0%   2-37
web_admin/routes/__init__.py           10     10     0%   2-12
web_admin/routes/auth.py               17     17     0%   2-26
web_admin/routes/clients.py            75     75     0%   2-139
web_admin/routes/dashboard.py          85     85     0%   2-181
web_admin/routes/debug.py               5      5     0%   2-9
web_admin/routes/purchases.py          55     55     0%   2-99
web_admin/routes/sellers.py            27     27     0%   2-46
web_admin/routes/sold.py               28     28     0%   2-49
web_admin/routes/stats.py               7      7     0%   2-21
web_admin/templates.py                 31     31     0%   2-38
-----------------------------------------------------------------
TOTAL                                2692   2204    18%
Coverage XML written to file coverage.xml

=========================== short test summary info ============================
ERROR tests/integration/test_preorder_flow.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
========================= 1 warning, 1 error in 4.65s ==========================
Error: Process completed with exit code 2.
