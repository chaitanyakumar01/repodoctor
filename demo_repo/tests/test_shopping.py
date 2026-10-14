import pytest
from shopping import Item, ShoppingCart, paginate_items, remove_item_by_name

def test_add_item():
    cart = ShoppingCart()
    cart.add_item(Item("Apple", 1.5))
    assert len(cart.items) == 1

def test_calculate_total_no_discount():
    cart = ShoppingCart()
    cart.add_item(Item("Apple", 1.5))
    cart.add_item(Item("Banana", 2.0))
    assert cart.calculate_total() == 3.5

def test_calculate_total_with_discount():
    cart = ShoppingCart()
    cart.add_item(Item("Apple", 15.0))
    cart.add_item(Item("Banana", 35.0))
    # Total is 50. 20% discount should be 10, so final is 40.
    assert cart.calculate_total(discount_percent=20.0) == 40.0

def test_calculate_total_with_large_discount():
    cart = ShoppingCart()
    cart.add_item(Item("Laptop", 1000.0))
    # 15% discount on 1000 is 150, final is 850
    assert cart.calculate_total(discount_percent=15.0) == 850.0

def test_get_most_expensive_item():
    cart = ShoppingCart()
    cart.add_item(Item("Apple", 1.5))
    cart.add_item(Item("Laptop", 1000.0))
    cart.add_item(Item("Banana", 2.0))
    item = cart.get_most_expensive_item()
    assert item is not None
    assert item.name == "Laptop"

def test_get_most_expensive_item_empty():
    cart = ShoppingCart()
    item = cart.get_most_expensive_item()
    assert item is None

def test_paginate_items_page_one():
    items = [Item(str(i), float(i)) for i in range(10)]
    page = paginate_items(items, page=1, page_size=4)
    assert len(page) == 4
    assert page[0].name == "0"
    assert page[-1].name == "3"

def test_paginate_items_page_two():
    items = [Item(str(i), float(i)) for i in range(10)]
    page = paginate_items(items, page=2, page_size=4)
    assert len(page) == 4
    assert page[0].name == "4"
    assert page[-1].name == "7"

def test_paginate_items_page_out_of_bounds():
    items = [Item(str(i), float(i)) for i in range(10)]
    page = paginate_items(items, page=99, page_size=4)
    assert len(page) == 0

def test_remove_item_by_name():
    items = [Item("Apple", 1.0), Item("Banana", 2.0), Item("Apple", 1.0)]
    filtered = remove_item_by_name(items, "Apple")
    assert len(filtered) == 1
    assert filtered[0].name == "Banana"
