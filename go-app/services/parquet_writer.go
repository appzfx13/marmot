package services

import (
	"fmt"
	"io"
	"os"
	"path/filepath"

	"github.com/parquet-go/parquet-go"
	"go-app/models"
)

// WriteChunkParquet writes a slice of MarketCandleRecord to a binary Parquet file with Snappy compression.
func WriteChunkParquet(filePath string, records []models.MarketCandleRecord) error {
	if len(records) == 0 {
		return nil
	}

	dir := filepath.Dir(filePath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("failed to create directory %s: %w", dir, err)
	}

	file, err := os.OpenFile(filePath, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0644)
	if err != nil {
		return fmt.Errorf("failed to open parquet chunk file %s: %w", filePath, err)
	}
	defer file.Close()

	writer := parquet.NewGenericWriter[models.MarketCandleRecord](
		file,
		parquet.Compression(&parquet.Snappy),
	)

	if _, err := writer.Write(records); err != nil {
		return fmt.Errorf("failed to write records to %s: %w", filePath, err)
	}

	if err := writer.Close(); err != nil {
		return fmt.Errorf("failed to close parquet writer for %s: %w", filePath, err)
	}

	return nil
}

// MergeParquetFiles merges multiple staged chunk Parquet files into a single consolidated Parquet file.
// Returns total rows written, final file size in MB, and error if any.
func MergeParquetFiles(outputFile string, sourceFiles []string) (int64, float64, error) {
	if len(sourceFiles) == 0 {
		return 0, 0, fmt.Errorf("no source parquet files to merge")
	}

	outDir := filepath.Dir(outputFile)
	if err := os.MkdirAll(outDir, 0755); err != nil {
		return 0, 0, fmt.Errorf("failed to create output directory %s: %w", outDir, err)
	}

	outFile, err := os.OpenFile(outputFile, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0644)
	if err != nil {
		return 0, 0, fmt.Errorf("failed to create consolidated parquet file %s: %w", outputFile, err)
	}
	defer outFile.Close()

	writer := parquet.NewGenericWriter[models.MarketCandleRecord](
		outFile,
		parquet.Compression(&parquet.Snappy),
	)

	var totalRows int64

	for _, srcPath := range sourceFiles {
		srcFile, err := os.Open(srcPath)
		if err != nil {
			continue // Skip unreadable chunk
		}

		reader := parquet.NewGenericReader[models.MarketCandleRecord](srcFile)
		buf := make([]models.MarketCandleRecord, 1024)

		for {
			n, readErr := reader.Read(buf)
			if n > 0 {
				if _, writeErr := writer.Write(buf[:n]); writeErr != nil {
					srcFile.Close()
					return totalRows, 0, fmt.Errorf("failed writing merged records: %w", writeErr)
				}
				totalRows += int64(n)
			}
			if readErr == io.EOF {
				break
			}
			if readErr != nil {
				break
			}
		}

		reader.Close()
		srcFile.Close()
	}

	if err := writer.Close(); err != nil {
		return totalRows, 0, fmt.Errorf("failed to close final parquet writer: %w", err)
	}

	// Calculate final file size in MB
	fileInfo, err := os.Stat(outputFile)
	var sizeMB float64
	if err == nil {
		sizeMB = float64(fileInfo.Size()) / (1024 * 1024)
	}

	return totalRows, sizeMB, nil
}

// VerifyParquetFile checks that a Parquet file exists, has valid magic bytes, and returns its row count and size.
func VerifyParquetFile(filePath string) (int64, float64, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return 0, 0, err
	}
	defer file.Close()

	fileInfo, err := file.Stat()
	if err != nil {
		return 0, 0, err
	}

	reader := parquet.NewGenericReader[models.MarketCandleRecord](file)
	defer reader.Close()

	numRows := reader.NumRows()
	sizeMB := float64(fileInfo.Size()) / (1024 * 1024)

	return numRows, sizeMB, nil
}
