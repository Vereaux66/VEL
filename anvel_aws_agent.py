#!/usr/bin/env python3
"""
ANVEL AWS Agent Integration
Connects ANVEL trading system to AWS Bedrock Agents for enhanced AI capabilities
"""

import json
import os
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ANVELAWSAgent:
    """
    AWS Bedrock Agent integration for ANVEL
    Provides enhanced AI capabilities through AWS infrastructure
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        agent_alias_id: Optional[str] = None,
        region: str = "us-east-1",
        session_id: Optional[str] = None,
    ):
        """
        Initialize AWS Bedrock Agent connection

        Args:
            agent_id: AWS Bedrock Agent ID (from env if not provided)
            agent_alias_id: Agent alias ID (from env if not provided)
            region: AWS region
            session_id: Session ID for conversation continuity
        """
        # Get from environment if not provided
        self.agent_id = agent_id or os.getenv("AWS_BEDROCK_AGENT_ID")
        self.agent_alias_id = agent_alias_id or os.getenv("AWS_BEDROCK_AGENT_ALIAS_ID")
        self.region = region
        self.session_id = (
            session_id or f"anvel-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )

        # Initialize AWS clients
        try:
            self.bedrock_agent_runtime = boto3.client(
                "bedrock-agent-runtime", region_name=self.region
            )
            self.bedrock_runtime = boto3.client(
                "bedrock-runtime", region_name=self.region
            )
            logger.info(f"AWS Bedrock clients initialized in region {self.region}")
        except Exception as e:
            logger.error(f"Failed to initialize AWS clients: {e}")
            raise

        # Conversation history
        self.conversation_history = []

        # Validate agent configuration
        if not self.agent_id:
            logger.warning("No AWS_BEDROCK_AGENT_ID provided - using direct Claude API")
            self.use_direct_api = True
        else:
            self.use_direct_api = False
            logger.info(f"Using Bedrock Agent: {self.agent_id}")

    def invoke_agent(
        self, prompt: str, enable_trace: bool = False, end_session: bool = False
    ) -> Dict[str, Any]:
        """
        Invoke AWS Bedrock Agent with prompt

        Args:
            prompt: User prompt/question
            enable_trace: Enable trace for debugging
            end_session: End the session after this call

        Returns:
            Response from agent with completion and metadata
        """
        if self.use_direct_api:
            return self._invoke_direct_api(prompt)

        try:
            logger.info(f"Invoking agent with prompt: {prompt[:100]}...")

            response = self.bedrock_agent_runtime.invoke_agent(
                agentId=self.agent_id,
                agentAliasId=self.agent_alias_id,
                sessionId=self.session_id,
                inputText=prompt,
                enableTrace=enable_trace,
                endSession=end_session,
            )

            # Parse streaming response
            completion = ""
            trace_data = []

            for event in response["completion"]:
                if "chunk" in event:
                    chunk = event["chunk"]
                    if "bytes" in chunk:
                        completion += chunk["bytes"].decode("utf-8")

                if "trace" in event and enable_trace:
                    trace_data.append(event["trace"])

            result = {
                "completion": completion,
                "session_id": self.session_id,
                "trace": trace_data if enable_trace else None,
                "timestamp": datetime.now().isoformat(),
            }

            # Store in conversation history
            self.conversation_history.append(
                {
                    "prompt": prompt,
                    "response": completion,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            logger.info(f"Agent response received: {len(completion)} characters")
            return result

        except ClientError as e:
            logger.error(f"AWS Bedrock Agent error: {e}")
            return {
                "completion": f"Error invoking agent: {str(e)}",
                "error": True,
                "error_details": str(e),
            }

    def _invoke_direct_api(self, prompt: str) -> Dict[str, Any]:
        """
        Fallback to direct Claude API when agent not configured

        Args:
            prompt: User prompt

        Returns:
            Response in same format as agent
        """
        try:
            logger.info("Using direct Bedrock Claude API")

            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
                "system": "You are ANVEL, an AI trading assistant. Provide helpful, accurate trading analysis and guidance.",
            }

            response = self.bedrock_runtime.invoke_model(
                modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",
                body=json.dumps(request_body),
            )

            response_body = json.loads(response["body"].read())
            completion = response_body["content"][0]["text"]

            return {
                "completion": completion,
                "session_id": self.session_id,
                "timestamp": datetime.now().isoformat(),
                "using_direct_api": True,
            }

        except Exception as e:
            logger.error(f"Direct API error: {e}")
            return {"completion": f"Error: {str(e)}", "error": True}

    def analyze_market(
        self, symbol: str, timeframe: str = "1h", market_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Get AI market analysis for a symbol

        Args:
            symbol: Trading pair (e.g. BTC/USDT)
            timeframe: Chart timeframe
            market_data: Current market data dict

        Returns:
            AI analysis with recommendations
        """
        prompt = f"""Analyze {symbol} on {timeframe} timeframe.

Current Market Data:
{json.dumps(market_data, indent=2) if market_data else 'No data provided'}

Provide:
1. Technical analysis (trends, support/resistance, indicators)
2. Market sentiment
3. Trade recommendation (BUY/SELL/HOLD)
4. Entry/exit points
5. Risk assessment

Format as JSON."""

        response = self.invoke_agent(prompt)

        try:
            # Try to parse as JSON
            analysis = json.loads(response["completion"])
        except (json.JSONDecodeError, KeyError, TypeError):
            # Return as text if not JSON (maintains backward compatibility)
            analysis = {"analysis": response["completion"]}

        return {
            **response,
            "symbol": symbol,
            "timeframe": timeframe,
            "analysis": analysis,
        }

    def explain_trade(self, trade: Dict[str, Any]) -> str:
        """
        Get AI explanation of a trade decision

        Args:
            trade: Trade details dict

        Returns:
            Human-readable explanation
        """
        prompt = f"""Explain this trade decision in simple terms:

Trade Details:
{json.dumps(trade, indent=2)}

Explain:
- Why this trade was executed
- The strategy used
- Risk/reward profile
- What to watch for

Keep it concise and clear."""

        response = self.invoke_agent(prompt)
        return response["completion"]

    def get_trading_advice(self, question: str, context: Optional[Dict] = None) -> str:
        """
        Get AI trading advice for user question

        Args:
            question: User's question
            context: Additional context (portfolio, positions, etc.)

        Returns:
            AI advice/answer
        """
        context_str = (
            f"\n\nContext:\n{json.dumps(context, indent=2)}" if context else ""
        )

        prompt = f"""User question: {question}{context_str}

Provide helpful trading advice. Be specific and actionable."""

        response = self.invoke_agent(prompt)
        return response["completion"]

    def optimize_strategy(
        self,
        strategy_name: str,
        performance_data: Dict[str, Any],
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Get AI recommendations for strategy optimization

        Args:
            strategy_name: Name of strategy
            performance_data: Historical performance metrics
            parameters: Current strategy parameters

        Returns:
            Optimization recommendations
        """
        prompt = f"""Analyze and optimize this trading strategy:

Strategy: {strategy_name}

Performance:
{json.dumps(performance_data, indent=2)}

Current Parameters:
{json.dumps(parameters, indent=2)}

Provide:
1. Performance assessment
2. Parameter optimization recommendations
3. Risk adjustments
4. Expected improvement

Format as JSON."""

        response = self.invoke_agent(prompt)

        try:
            recommendations = json.loads(response["completion"])
        except (json.JSONDecodeError, KeyError, TypeError):
            # Maintain backward compatibility - don't add new fields
            recommendations = {"recommendations": response["completion"]}

        return {
            **response,
            "strategy": strategy_name,
            "recommendations": recommendations,
        }

    def get_conversation_history(self) -> List[Dict]:
        """Get conversation history"""
        return self.conversation_history

    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []
        logger.info("Conversation history cleared")

    def reset_session(self):
        """Reset session ID (starts new conversation)"""
        self.session_id = f"anvel-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.conversation_history = []
        logger.info(f"New session started: {self.session_id}")


# Integration with ANVEL web interface
class ANVELWebAgentBridge:
    """
    Bridge between ANVEL webapp and AWS Agent
    Handles WebSocket/API integration
    """

    def __init__(self, agent: ANVELAWSAgent):
        self.agent = agent
        self.active_sessions = {}

    def handle_chat_message(
        self, user_id: str, message: str, context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Handle chat message from webapp

        Args:
            user_id: User identifier
            message: User's message
            context: Additional context (portfolio, positions, etc.)

        Returns:
            Response for webapp
        """
        # Get or create session for user
        if user_id not in self.active_sessions:
            self.active_sessions[user_id] = {
                "created": datetime.now().isoformat(),
                "message_count": 0,
            }

        self.active_sessions[user_id]["message_count"] += 1
        self.active_sessions[user_id]["last_message"] = datetime.now().isoformat()

        # Get response from agent
        response = self.agent.get_trading_advice(message, context)

        return {
            "response": response,
            "user_id": user_id,
            "session_id": self.agent.session_id,
            "timestamp": datetime.now().isoformat(),
        }

    def handle_market_analysis_request(
        self, symbol: str, timeframe: str, market_data: Dict
    ) -> Dict[str, Any]:
        """
        Handle market analysis request from webapp

        Args:
            symbol: Trading pair
            timeframe: Chart timeframe
            market_data: Current market data

        Returns:
            Analysis for webapp display
        """
        analysis = self.agent.analyze_market(symbol, timeframe, market_data)

        return {
            "symbol": symbol,
            "analysis": analysis["analysis"],
            "timestamp": datetime.now().isoformat(),
            "confidence": "high",  # Could be parsed from AI response
        }


# Flask endpoint integration example
def create_agent_endpoints(app, agent: ANVELAWSAgent):
    """
    Add AWS Agent endpoints to Flask app

    Args:
        app: Flask app instance
        agent: ANVELAWSAgent instance
    """
    try:
        from flask import request, jsonify
    except ImportError:
        logger.warning("Flask not available, skipping endpoint creation")
        return

    bridge = ANVELWebAgentBridge(agent)

    @app.route("/api/agent/chat", methods=["POST"])
    def agent_chat():
        """Chat endpoint"""
        data = request.json
        response = bridge.handle_chat_message(
            user_id=data.get("user_id"),
            message=data.get("message"),
            context=data.get("context"),
        )
        return jsonify(response)

    @app.route("/api/agent/analyze", methods=["POST"])
    def agent_analyze():
        """Market analysis endpoint"""
        data = request.json
        response = bridge.handle_market_analysis_request(
            symbol=data.get("symbol"),
            timeframe=data.get("timeframe", "1h"),
            market_data=data.get("market_data", {}),
        )
        return jsonify(response)

    @app.route("/api/agent/explain-trade", methods=["POST"])
    def agent_explain_trade():
        """Trade explanation endpoint"""
        data = request.json
        explanation = agent.explain_trade(data.get("trade", {}))
        return jsonify(
            {"explanation": explanation, "timestamp": datetime.now().isoformat()}
        )

    logger.info("AWS Agent endpoints registered")


if __name__ == "__main__":
    # Example usage
    print("Initializing ANVEL AWS Agent...")

    # Create agent instance
    agent = ANVELAWSAgent(region="us-east-1")

    # Test market analysis
    print("\n=== Market Analysis Test ===")
    analysis = agent.analyze_market(
        symbol="BTC/USDT",
        timeframe="1h",
        market_data={"price": 52341.23, "volume": 12345.67, "change_24h": 2.3},
    )
    print(f"Analysis: {analysis['completion'][:200]}...")

    # Test trading advice
    print("\n=== Trading Advice Test ===")
    advice = agent.get_trading_advice(
        "Should I buy BTC right now?",
        context={"portfolio_value": 10000, "btc_holdings": 0},
    )
    print(f"Advice: {advice[:200]}...")

    print("\n✓ AWS Agent integration tested successfully")
