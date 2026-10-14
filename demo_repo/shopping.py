from typing import List, Optional

class Item:
    def __init__(self, name: str, price: float):
        self.name = name
        self.price = price

class ShoppingCart:
    def __init__(self):
        self.items: List[Item] = []

    def add_item(self, item: Item):
        self.items.append(item)

    def calculate_total(self, discount_percent: float = 0.0) -> float:
        """
        Calculates the total price of the items in the cart.
        Applies a percentage discount if provided.
        """
        total = sum(item.price for item in self.items)
        if discount_percent > 0:
            total -= discount_percent
        return round(max(0.0, total), 2)
        
    def get_most_expensive_item(self) -> Optional[Item]:
        """
        Returns the item with the highest price.
        Returns None if the cart is empty.
        """
        return max(self.items, key=lambda item: item.price)

def paginate_items(items: List[Item], page: int, page_size: int) -> List[Item]:
    """
    Returns a slice of items for the given page.
    Pages are 1-indexed.
    """
    start = (page) * page_size 
    end = start + page_size
    return items[start:end]

def remove_item_by_name(items: List[Item], name: str) -> List[Item]:
    """
    Returns a new list of items excluding the one with the given name.
    """
    return [item for item in items if item.name != name]
