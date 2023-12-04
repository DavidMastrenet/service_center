SELECT 'center_dev';

CREATE TABLE `user` (
  `uid` VARCHAR(20) PRIMARY KEY,
  `name` VARCHAR(20),
  `password` VARCHAR(128),
  `tag` VARCHAR(20),
  `isAdmin` TINYINT
);

CREATE TABLE `checkin_task` (
  `taskId` INT AUTO_INCREMENT PRIMARY KEY,
  `taskName` VARCHAR(50),
  `expireTime` DATETIME,
  `uid` VARCHAR(20),
  FOREIGN KEY (`uid`) REFERENCES `user`(`uid`)
);

CREATE TABLE `checkin_record` (
  `recordId` INT AUTO_INCREMENT PRIMARY KEY,
  `taskId` INT,
  `uid` VARCHAR(20),
  `longitude` DOUBLE,
  `latitude` DOUBLE,
  `time` DATETIME,
  `note` VARCHAR(128),
  FOREIGN KEY (`taskId`) REFERENCES `checkin_task`(`taskId`),
  FOREIGN KEY (`uid`) REFERENCES `user`(`uid`)
);

CREATE TABLE `collect_task` (
  `taskId` INT AUTO_INCREMENT PRIMARY KEY,
  `taskName` VARCHAR(50),
  `taskType` VARCHAR(50),
  `expireTime` DATETIME,
  `uid` VARCHAR(20),
  FOREIGN KEY (`uid`) REFERENCES `user`(`uid`)
);

CREATE TABLE `collect_record` (
  `recordId` INT AUTO_INCREMENT PRIMARY KEY,
  `taskId` INT,
  `uid` VARCHAR(20),
  `content` VARCHAR(1024),
  `time` DATETIME,
  FOREIGN KEY (`taskId`) REFERENCES `collect_task`(`taskId`),
  FOREIGN KEY (`uid`) REFERENCES `user`(`uid`)
);


CREATE TABLE `user_role` (
  `uid` VARCHAR(20),
  `role` VARCHAR(20),
  `createdBy` VARCHAR(20),
  FOREIGN KEY (`uid`) REFERENCES `user`(`uid`)
);


CREATE TABLE `log` (
  `uid` VARCHAR(20),
  `info` VARCHAR(1024),
  `time` DATETIME,
  FOREIGN KEY (`uid`) REFERENCES `user`(`uid`)
);


CREATE TABLE bbs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  content VARCHAR(1024),
  time DATETIME DEFAULT CURRENT_TIMESTAMP
);