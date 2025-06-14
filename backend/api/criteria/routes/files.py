"""
Criteria Analysis Routes - Files Management

Содержит endpoints для управления файлами критериев:
- GET /files - список всех файлов критериев
- GET /files/{filename} - содержимое файла
- PUT /files/{filename} - обновление файла
- POST /files - создание нового файла
- POST /upload - загрузка файла
- DELETE /files/{filename} - удаление файла
"""

import aiofiles
import pandas as pd
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, File, UploadFile, HTTPException

from ..common import (
    logger, CRITERIA_PROCESSOR_PATH
)

router = APIRouter()

@router.get("/files")
async def get_criteria_files():
    """Получить список всех файлов критериев с информацией о продуктах"""
    criteria_dir = CRITERIA_PROCESSOR_PATH / "criteria"
    
    if not criteria_dir.exists():
        return {"files": [], "products": []}
    
    files = []
    all_products = set()
    
    # Поддерживаем как CSV, так и XLSX файлы
    for pattern in ["*.csv", "*.xlsx"]:
        for file_path in criteria_dir.glob(pattern):
            # Исключаем backup файлы из отображения (на случай если они остались от старых версий)
            if ".backup_" in file_path.name or ".deleted_" in file_path.name:
                continue
            try:
                # Читаем файл в зависимости от расширения
                if file_path.suffix.lower() == '.csv':
                    df = pd.read_csv(file_path)
                elif file_path.suffix.lower() == '.xlsx':
                    df = pd.read_excel(file_path)
                else:
                    continue  # Пропускаем неподдерживаемые файлы
                
                # ФИЛЬТРАЦИЯ ПУСТЫХ СТРОК для правильного подсчета
                # Основные колонки для критериев
                main_columns = ['Product', 'Criteria', 'Target Audience']
                existing_columns = [col for col in main_columns if col in df.columns]
                
                if existing_columns:
                    # Удаляем строки где ВСЕ основные колонки пустые
                    df_filtered = df.dropna(subset=existing_columns, how='all')
                    df_filtered = df_filtered[df_filtered[existing_columns].ne('').any(axis=1)]
                    actual_rows = len(df_filtered)
                else:
                    # Если нет основных колонок, считаем все непустые строки
                    actual_rows = len(df.dropna(how='all'))
                
                # Извлекаем продукты из файла
                file_products = []
                if 'Product' in df.columns:
                    file_products = df['Product'].unique().tolist()
                    # Убираем NaN значения
                    file_products = [p for p in file_products if pd.notna(p) and str(p).strip()]
                    all_products.update(file_products)
                
                files.append({
                    "filename": file_path.name,
                    "full_path": str(file_path),
                    "size": file_path.stat().st_size,
                    "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                    "rows_preview": min(5, actual_rows),  # Показываем до 5 строк для preview
                    "total_rows": actual_rows,  # РЕАЛЬНОЕ количество строк с данными
                    "columns": list(df.columns) if not df.empty else [],
                    "products": file_products  # Продукты в этом файле
                })
            except Exception as e:
                logger.error(f"Error reading criteria file {file_path}: {e}")
                files.append({
                    "filename": file_path.name,
                    "full_path": str(file_path),
                    "size": file_path.stat().st_size,
                    "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                    "error": str(e),
                    "products": []
                })
    
    return {
        "files": files,
        "products": sorted(list(all_products))  # Все уникальные продукты
    }

@router.get("/files/{filename}")
async def get_criteria_file_content(filename: str):
    """Получить содержимое файла критериев"""
    criteria_dir = CRITERIA_PROCESSOR_PATH / "criteria"
    file_path = criteria_dir / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Criteria file not found")
    
    if not file_path.suffix.lower() == '.csv':
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    
    try:
        df = pd.read_csv(file_path)
        
        # Заменяем NaN и Infinity значения на None/null для корректной JSON сериализации
        df = df.replace([float('inf'), float('-inf')], None)
        df = df.where(pd.notnull(df), None)
        
        return {
            "filename": filename,
            "columns": list(df.columns),
            "data": df.to_dict('records'),
            "total_rows": len(df),
            "file_info": {
                "size": file_path.stat().st_size,
                "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
            }
        }
    except Exception as e:
        logger.error(f"Error reading criteria file {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")

@router.put("/files/{filename}")
async def update_criteria_file(filename: str, file_data: dict):
    """Обновить содержимое файла критериев"""
    criteria_dir = CRITERIA_PROCESSOR_PATH / "criteria"
    file_path = criteria_dir / filename
    
    if not filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    
    try:
        # Валидируем структуру данных
        if "data" not in file_data or "columns" not in file_data:
            raise HTTPException(status_code=400, detail="Invalid data format. Expected 'data' and 'columns' fields")
        
        # Создаем DataFrame из переданных данных
        df = pd.DataFrame(file_data["data"], columns=file_data["columns"])
        
        # НЕ создаем backup файлы - пользователи их все равно не смогут достать
        
        # Сохраняем новый файл
        df.to_csv(file_path, index=False)
        
        logger.info(f"Updated criteria file: {filename}")
        
        return {
            "message": "File updated successfully",
            "filename": filename,
            "rows_saved": len(df),
            "timestamp": datetime.now().isoformat()
        }
        
    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="Empty data provided")
    except Exception as e:
        logger.error(f"Error updating criteria file {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating file: {str(e)}")

@router.post("/files")
async def create_criteria_file(file_data: dict):
    """Создать новый файл критериев"""
    criteria_dir = CRITERIA_PROCESSOR_PATH / "criteria"
    
    if "filename" not in file_data:
        raise HTTPException(status_code=400, detail="Filename is required")
    
    filename = file_data["filename"]
    if not filename.endswith('.csv'):
        filename += '.csv'
    
    file_path = criteria_dir / filename
    
    if file_path.exists():
        raise HTTPException(status_code=400, detail="File already exists")
    
    try:
        # Создаем DataFrame с данными или пустой шаблон
        if "data" in file_data and "columns" in file_data:
            df = pd.DataFrame(file_data["data"], columns=file_data["columns"])
        else:
            # Создаем стандартный шаблон для критериев
            df = pd.DataFrame(columns=[
                "Product", "Target Audience", "Criteria Type", "Criteria", 
                "Place", "Search Query", "Signals"
            ])
            # Добавляем примерную строку
            df.loc[0] = [
                "New Product", "Target Audience", "Qualification", 
                "Sample criteria", "description", "sample query", "sample signals"
            ]
        
        df.to_csv(file_path, index=False)
        
        logger.info(f"Created new criteria file: {filename}")
        
        return {
            "message": "File created successfully",
            "filename": filename,
            "rows_created": len(df),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error creating criteria file {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating file: {str(e)}")

@router.post("/upload")
async def upload_criteria_file(file: UploadFile = File(...)):
    """Загрузить файл критериев через multipart/form-data"""
    criteria_dir = CRITERIA_PROCESSOR_PATH / "criteria"
    
    # Проверяем формат файла
    if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(
            status_code=400, 
            detail="Unsupported file format. Use CSV or Excel files."
        )
    
    file_path = criteria_dir / file.filename
    
    if file_path.exists():
        raise HTTPException(status_code=400, detail="File already exists")
    
    try:
        # Сохраняем загруженный файл
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        logger.info(f"Uploaded criteria file: {file.filename}")
        
        return {
            "message": "File uploaded successfully",
            "filename": file.filename,
            "size": len(content),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error uploading criteria file {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")

@router.delete("/files/{filename}")
async def delete_criteria_file(filename: str):
    """Удалить файл критериев"""
    criteria_dir = CRITERIA_PROCESSOR_PATH / "criteria"
    file_path = criteria_dir / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Criteria file not found")
    
    try:
        # Удаляем файл БЕЗ создания backup
        file_path.unlink()
        
        logger.info(f"Deleted criteria file: {filename}")
        
        return {
            "message": "File deleted successfully",
            "filename": filename,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error deleting criteria file {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}") 