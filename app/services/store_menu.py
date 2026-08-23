"""대표메뉴 로직 (API명세서 3.2)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.store import Store
from app.models.store_menu import StoreMenu
from app.schemas.store import MenuCreateRequest, MenuUpdateRequest


class MenuNotFound(NotFoundError):
    error_code = "MENU_NOT_FOUND"
    message = "메뉴를 찾을 수 없습니다."


def list_menus(db: Session, store: Store) -> list[StoreMenu]:
    return list(
        db.scalars(select(StoreMenu).where(StoreMenu.store_id == store.id).order_by(StoreMenu.id))
    )


def create_menu(db: Session, store: Store, payload: MenuCreateRequest) -> StoreMenu:
    menu = StoreMenu(store_id=store.id, **payload.model_dump())
    db.add(menu)
    db.commit()
    db.refresh(menu)
    return menu


def get_menu(db: Session, store: Store, menu_id: int) -> StoreMenu:
    """가게에 속한 메뉴를 가져온다.

    경로의 `storeId`와 메뉴의 `store_id`가 다르면 404다. 소유권 검증은 상위에서
    이미 끝났지만, 그것만으로는 **내 가게 경로로 남의 가게 메뉴를 조회**하는 걸 못 막는다.
    """
    menu = db.get(StoreMenu, menu_id)
    if menu is None or menu.store_id != store.id:
        raise MenuNotFound
    return menu


def update_menu(db: Session, menu: StoreMenu, payload: MenuUpdateRequest) -> StoreMenu:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(menu, field, value)
    db.commit()
    db.refresh(menu)
    return menu


def delete_menu(db: Session, menu: StoreMenu) -> None:
    db.delete(menu)
    db.commit()
