import React, { useState, useRef } from 'react';
import { config } from './core/config';

const FileUpload = () => {
  const [selectedFile, setSelectedFile] = useState<any>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<any>(null);

  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file) {
      setSelectedFile(file);
      console.log('File đã chọn:', file.name);
      handleUploadFile(file);
    }
  };

  const handleDragEnter = (event) => {
    event.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (event) => {
    event.preventDefault();
    setIsDragging(false);
  };

  const handleDragOver = (event) => {
    event.preventDefault();
  };

  const handleDrop = (event) => {
    event.preventDefault();
    setIsDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) {
      setSelectedFile(file);
      console.log('File đã thả:', file.name);
      handleUploadFile(file);
    }
  };

  const handleDivClick = () => {
    fileInputRef.current!.click();
  };

  const handleUploadFile = async (file) => {
    const formData = new FormData();
    formData.append(
      'file',
      file,
      file.name
    );
    console.log("Đang gửi ảnh")
    try{
      
      const response = await fetch(`${config.apiUrl}/v1/document`,{
        method: 'post',
        body: formData
      });

      console.log(response)

    }catch (error){
      console.log(error)
    }
  };

  return (
    <div
      className={`upload-container ${isDragging ? 'dragging' : ''}`}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      onClick={handleDivClick}
    >
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        style={{ display: 'none' }} // Ẩn input mặc định
      />
      {selectedFile ? (
        <p>File đã chọn: <strong>{selectedFile.name}</strong></p>
      ) : (
        <>
          <p>Kéo và thả file vào đây hoặc nhấp để chọn file</p>
          <p className="upload-icon">&#x2193;</p> {/* Biểu tượng mũi tên xuống hoặc icon khác */}
        </>
      )}
    </div>
  );
};

export default FileUpload;