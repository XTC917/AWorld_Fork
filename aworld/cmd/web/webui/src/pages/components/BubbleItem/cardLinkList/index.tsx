import { CheckOutlined, SearchOutlined } from '@ant-design/icons';
import { Card, Flex, Tag, Typography } from 'antd';
import React from 'react';
import type { ToolCardData } from '../utils';
import './index.less';

interface Props {
  sessionId: string;
  data: ToolCardData;
}

interface ItemInterface {
  title: string;
  snippet: string;
  link?: string;
}

const cardLinkList: React.FC<Props> = ({ data }) => {
  const items = data?.card_data?.search_items || [];
  const cardItems = items;
  return (
    <div className="cardwrap bg">
      {items.length > 0 && (
        <Flex justify="space-between" align="center" className="card-length">
          <Tag icon={<SearchOutlined />}>{`search keywords: ${data?.card_data?.query || ''}`}</Tag>
          <Flex align="center">
            <CheckOutlined className="check-icon" />
            {items.length} results
          </Flex>
        </Flex>
      )}
      <div className="border-box">
        <Flex className="cardbox">
          {cardItems.map((item: ItemInterface, index: number) => (
            <Card title={item.title} key={index} className="card-item" onClick={() => item.link && window.open(item.link, '_blank', 'noopener,noreferrer')}>
              <Typography.Paragraph className="desc" ellipsis={{ rows: 3, tooltip: item.snippet }}>
                {item.snippet}
              </Typography.Paragraph>
              <Typography.Text ellipsis={{ tooltip: item.link }}>{item.link}</Typography.Text>
            </Card>
          ))}
        </Flex>
      </div>
    </div>
  );
};

export default cardLinkList;
